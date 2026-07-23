"""Billing endpoints backed by Stripe Checkout, the Customer Portal, and webhooks.

Signup flow: POST checkout/ creates an INACTIVE client user and a Checkout
Session; the user is only activated by the checkout.session.completed webhook
once payment succeeds. Payment failure NEVER deactivates the user -- past_due
only drives a banner in the UI (ratified rule).
"""

from datetime import datetime, timezone as dt_timezone

import stripe
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.db import IntegrityError, transaction
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from stripe import SignatureVerificationError, StripeError

from accounts.constants import ROLE_CLIENT
from notifications.emails import send_welcome_email
from notifications.ntfy import notify_new_paid_signup

from .catalog import parse_lookup_key, plan_catalog, price_lookup_key
from .models import Customer, PortalConfiguration, Subscription
from .permissions import ClientOnlyPermission
from .serializers import (
    FLOW_SUBSCRIPTION_CANCEL,
    FLOW_SUBSCRIPTION_UPDATE,
    CheckoutSerializer,
    PortalSerializer,
    SubscriptionSerializer,
)


def get_stripe():
    """Return the stripe module configured with the secret key from settings."""
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


class BillingConfigView(APIView):
    """Public billing config for the signup page: publishable key + plan catalog."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses=None)
    def get(self, request):
        return Response(
            {
                "publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
                "plans": plan_catalog(),
            }
        )


class CheckoutView(APIView):
    """Self-serve signup: create an inactive client user and a Checkout Session.

    An existing INACTIVE user with the same email (an earlier abandoned
    checkout) is reused; an existing active user gets a 409 telling them to
    log in instead.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "billing_checkout"
    serializer_class = CheckoutSerializer

    @extend_schema(request=CheckoutSerializer, responses=None)
    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        email = data["email"].lower()

        existing = User.objects.filter(email__iexact=email).first()
        conflict = Response(
            {"detail": "An account with this email already exists. Please log in instead."},
            status=status.HTTP_409_CONFLICT,
        )
        if existing and existing.is_active:
            return conflict
        # Only a pending self-serve signup may be reused. A deactivated
        # coach/admin/staff account must never be hijacked into a client
        # signup (password reset + webhook reactivation = takeover).
        if existing and (
            existing.is_staff
            or existing.is_superuser
            or existing.groups.exclude(name=ROLE_CLIENT).exists()
        ):
            return conflict
        if existing is None and User.objects.filter(username__iexact=email).exists():
            return conflict

        first_name, _, last_name = data["full_name"].strip().partition(" ")
        try:
            with transaction.atomic():
                if existing:
                    user = existing
                    user.first_name = first_name
                    user.last_name = last_name
                    user.set_password(data["password"])
                    user.save()
                else:
                    user = User.objects.create_user(
                        username=email,
                        email=email,
                        password=data["password"],
                        first_name=first_name,
                        last_name=last_name,
                        is_active=False,
                    )
                user.groups.set([Group.objects.get(name=ROLE_CLIENT)])
        except IntegrityError:
            # Two concurrent signups with the same email: the loser hits the
            # unique username constraint.
            return conflict

        api = get_stripe()
        try:
            customer = Customer.objects.filter(user=user).first()
            if customer is None:
                stripe_customer = api.Customer.create(
                    email=email,
                    name=data["full_name"].strip(),
                    metadata={"user_id": str(user.id)},
                )
                customer = Customer.objects.create(
                    user=user, stripe_customer_id=stripe_customer["id"]
                )

            lookup_key = price_lookup_key(data["plan"], data["interval"])
            prices = api.Price.list(lookup_keys=[lookup_key], active=True, limit=1)
            price_list = prices["data"]
            if not price_list:
                return Response(
                    {"detail": "This plan is not available yet. Please try again later."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            session = api.checkout.Session.create(
                mode="subscription",
                customer=customer.stripe_customer_id,
                line_items=[{"price": price_list[0]["id"], "quantity": 1}],
                client_reference_id=str(user.id),
                success_url=(
                    f"{settings.APP_BASE_URL}/billing/success"
                    "?session_id={CHECKOUT_SESSION_ID}"
                ),
                cancel_url=f"{settings.APP_BASE_URL}/signup",
            )
        except StripeError:
            return Response(
                {"detail": "We could not start checkout. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({"url": session["url"]})


class PortalView(APIView):
    """Create a Stripe Billing Portal session, optionally deep-linked to a flow."""

    permission_classes = [IsAuthenticated, ClientOnlyPermission]
    serializer_class = PortalSerializer

    @extend_schema(request=PortalSerializer, responses=None)
    def post(self, request):
        serializer = PortalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        flow = serializer.validated_data.get("flow")

        customer = Customer.objects.filter(user=request.user).first()
        if customer is None:
            return Response(
                {"detail": "No billing account found for this user."},
                status=status.HTTP_404_NOT_FOUND,
            )

        params = {
            "customer": customer.stripe_customer_id,
            "return_url": f"{settings.APP_BASE_URL}/app",
        }
        portal_config = PortalConfiguration.load()
        if portal_config.stripe_configuration_id:
            params["configuration"] = portal_config.stripe_configuration_id

        if flow:
            flow_data = {"type": flow}
            if flow in (FLOW_SUBSCRIPTION_UPDATE, FLOW_SUBSCRIPTION_CANCEL):
                subscription = Subscription.objects.filter(user=request.user).first()
                if subscription is None:
                    return Response(
                        {"detail": "No subscription found for this user."},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                flow_data[flow] = {"subscription": subscription.stripe_subscription_id}
            params["flow_data"] = flow_data

        api = get_stripe()
        try:
            session = api.billing_portal.Session.create(**params)
        except StripeError:
            return Response(
                {"detail": "We could not open the billing portal. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({"url": session["url"]})


class SubscriptionView(APIView):
    """Current user's subscription, or null when they have none."""

    permission_classes = [IsAuthenticated]
    serializer_class = SubscriptionSerializer

    @extend_schema(responses=SubscriptionSerializer)
    def get(self, request):
        subscription = Subscription.objects.filter(user=request.user).first()
        if subscription is None:
            return Response(None)
        return Response(SubscriptionSerializer(subscription).data)


def sget(obj, key, default=None):
    """dict.get that also works on stripe StripeObject instances.

    Newer stripe-python objects implement __getitem__ but not ``.get``;
    plain dicts (and our test doubles) work identically through this path.
    """
    if obj is None:
        return default
    try:
        value = obj[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None else value


def _subscription_defaults(stripe_subscription):
    """Extract local Subscription fields from a Stripe subscription payload."""
    items = sget(sget(stripe_subscription, "items"), "data") or []
    first_item = items[0] if items else {}
    price = sget(first_item, "price") or {}
    lookup_key = sget(price, "lookup_key") or ""
    plan, interval = parse_lookup_key(lookup_key)
    # Newer Stripe API versions report the period on the subscription item.
    period_end = sget(stripe_subscription, "current_period_end") or sget(
        first_item, "current_period_end"
    )
    defaults = {
        "stripe_subscription_id": stripe_subscription["id"],
        "price_lookup_key": lookup_key,
        "status": sget(stripe_subscription, "status") or "",
        "cancel_at_period_end": bool(sget(stripe_subscription, "cancel_at_period_end")),
        "current_period_end": (
            datetime.fromtimestamp(period_end, tz=dt_timezone.utc) if period_end else None
        ),
    }
    if plan:
        defaults["plan"] = plan
        defaults["interval"] = interval
    payment_method = sget(stripe_subscription, "default_payment_method")
    card = sget(payment_method, "card") or {}
    if sget(card, "last4"):
        defaults["card_brand"] = sget(card, "brand") or ""
        defaults["card_last4"] = card["last4"]
    return defaults


def _handle_checkout_completed(session):
    user_id = sget(session, "client_reference_id")
    if not user_id:
        return
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        return
    # The inactive -> active transition happens exactly once per signup, so it
    # gates the welcome email and the ntfy ping against webhook replays.
    newly_activated = not user.is_active
    if not user.is_active:
        user.is_active = True
        user.save(update_fields=["is_active"])
    customer_id = sget(session, "customer")
    if customer_id:
        Customer.objects.update_or_create(
            user=user, defaults={"stripe_customer_id": customer_id}
        )
    subscription = None
    subscription_id = sget(session, "subscription")
    if subscription_id:
        if not isinstance(subscription_id, str):
            subscription_id = sget(subscription_id, "id")
        stripe_subscription = get_stripe().Subscription.retrieve(
            subscription_id, expand=["default_payment_method"]
        )
        subscription, _ = Subscription.objects.update_or_create(
            user=user, defaults=_subscription_defaults(stripe_subscription)
        )
    if newly_activated:
        plan_name = subscription.get_plan_display() if subscription and subscription.plan else ""
        send_welcome_email(user, plan_name)
        notify_new_paid_signup(user.email, plan_name or "unknown plan")


def _handle_subscription_change(stripe_subscription, deleted=False):
    subscription = Subscription.objects.filter(
        stripe_subscription_id=stripe_subscription["id"]
    ).first()
    if subscription is None:
        return
    # Deletion is terminal in Stripe; webhook delivery order is not
    # guaranteed, so a late "updated" event must not resurrect the record.
    if subscription.status == Subscription.STATUS_CANCELED and not deleted:
        return
    defaults = _subscription_defaults(stripe_subscription)
    if deleted:
        defaults["status"] = Subscription.STATUS_CANCELED
    for field, value in defaults.items():
        setattr(subscription, field, value)
    subscription.save()


def _handle_payment_failed(invoice):
    subscription_id = sget(invoice, "subscription")
    if not subscription_id:
        # Newer Stripe API versions nest the subscription under invoice.parent.
        parent = sget(invoice, "parent") or {}
        details = sget(parent, "subscription_details") or {}
        subscription_id = sget(details, "subscription")
    if subscription_id is not None and not isinstance(subscription_id, str):
        subscription_id = sget(subscription_id, "id")
    if not subscription_id:
        return
    subscription = Subscription.objects.filter(
        stripe_subscription_id=subscription_id
    ).first()
    if subscription is None:
        return
    # Banner-only by design: mark past_due, never touch user.is_active.
    subscription.status = Subscription.STATUS_PAST_DUE
    subscription.save(update_fields=["status", "updated_at"])


class StripeWebhookView(APIView):
    """Stripe webhook receiver: signature-verified, idempotent, unknown events → 200."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(request=None, responses=None)
    def post(self, request):
        try:
            event = stripe.Webhook.construct_event(
                request.body,
                request.META.get("HTTP_STRIPE_SIGNATURE", ""),
                settings.STRIPE_WEBHOOK_SECRET,
            )
        except (ValueError, SignatureVerificationError):
            return Response(
                {"detail": "Invalid webhook payload or signature."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        event_type = event["type"]
        data_object = event["data"]["object"]
        if event_type == "checkout.session.completed":
            _handle_checkout_completed(data_object)
        elif event_type in (
            "customer.subscription.updated",
            "customer.subscription.deleted",
        ):
            _handle_subscription_change(
                data_object, deleted=event_type.endswith("deleted")
            )
        elif event_type == "invoice.payment_failed":
            _handle_payment_failed(data_object)
        return Response({"received": True})
