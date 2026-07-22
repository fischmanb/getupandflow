from unittest import mock

from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from stripe import SignatureVerificationError

from accounts.constants import ROLE_CLIENT, ROLE_COACH

from .models import Customer, PortalConfiguration, Subscription

PERIOD_END = 1893456000  # 2030-01-01T00:00:00Z


def stripe_subscription_payload(
    sub_id="sub_123",
    lookup_key="full_support_monthly",
    sub_status="active",
    cancel_at_period_end=False,
    period_end=PERIOD_END,
    card=None,
):
    payload = {
        "id": sub_id,
        "status": sub_status,
        "cancel_at_period_end": cancel_at_period_end,
        "items": {
            "data": [
                {
                    "price": {"lookup_key": lookup_key},
                    "current_period_end": period_end,
                }
            ]
        },
    }
    if card:
        payload["default_payment_method"] = {"card": card}
    return payload


def webhook_event(event_type, data_object):
    return {"type": event_type, "data": {"object": data_object}}


class BillingConfigTests(APITestCase):
    def test_config_is_public_and_lists_plans(self):
        response = self.client.get(reverse("billing-config"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("publishable_key", response.data)
        plans = {plan["id"]: plan for plan in response.data["plans"]}
        self.assertEqual(set(plans), {"full_support", "focus_lite"})
        self.assertEqual(plans["full_support"]["prices"]["monthly"]["amount"], 750)
        self.assertEqual(plans["focus_lite"]["prices"]["weekly"]["amount"], 95)


@mock.patch("billing.views.stripe")
class CheckoutTests(APITestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def configure(self, mock_stripe):
        mock_stripe.Customer.create.return_value = {"id": "cus_123"}
        mock_stripe.Price.list.return_value = {"data": [{"id": "price_123"}]}
        mock_stripe.checkout.Session.create.return_value = {
            "url": "https://checkout.stripe.com/c/pay/cs_test_123"
        }

    def checkout_payload(self, **overrides):
        payload = {
            "email": "newclient@example.com",
            "full_name": "New Client",
            "password": "Pass12345!",
            "plan": "full_support",
            "interval": "monthly",
        }
        payload.update(overrides)
        return payload

    def test_checkout_creates_inactive_client_user(self, mock_stripe):
        self.configure(mock_stripe)
        response = self.client.post(reverse("billing-checkout"), self.checkout_payload())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["url"], "https://checkout.stripe.com/c/pay/cs_test_123")

        user = User.objects.get(email="newclient@example.com")
        self.assertFalse(user.is_active)
        self.assertEqual(user.first_name, "New")
        self.assertEqual(user.last_name, "Client")
        self.assertTrue(user.groups.filter(name=ROLE_CLIENT).exists())
        self.assertEqual(user.billing_customer.stripe_customer_id, "cus_123")

        session_kwargs = mock_stripe.checkout.Session.create.call_args.kwargs
        self.assertEqual(session_kwargs["mode"], "subscription")
        self.assertEqual(session_kwargs["client_reference_id"], str(user.id))
        self.assertEqual(session_kwargs["customer"], "cus_123")
        price_kwargs = mock_stripe.Price.list.call_args.kwargs
        self.assertEqual(price_kwargs["lookup_keys"], ["full_support_monthly"])

    def test_checkout_reuses_inactive_unpaid_user(self, mock_stripe):
        self.configure(mock_stripe)
        first = self.client.post(reverse("billing-checkout"), self.checkout_payload())
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        second = self.client.post(
            reverse("billing-checkout"),
            self.checkout_payload(full_name="Renamed Client", plan="focus_lite", interval="weekly"),
        )
        self.assertEqual(second.status_code, status.HTTP_200_OK)

        users = User.objects.filter(email="newclient@example.com")
        self.assertEqual(users.count(), 1)
        self.assertEqual(users.first().first_name, "Renamed")
        self.assertFalse(users.first().is_active)
        # The Stripe customer from the first attempt is reused, not recreated.
        self.assertEqual(mock_stripe.Customer.create.call_count, 1)
        self.assertEqual(Customer.objects.count(), 1)

    def test_checkout_active_email_returns_conflict(self, mock_stripe):
        self.configure(mock_stripe)
        User.objects.create_user(
            username="existing", email="newclient@example.com", password="Pass12345!"
        )
        response = self.client.post(reverse("billing-checkout"), self.checkout_payload())
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("log in", response.data["detail"])
        mock_stripe.checkout.Session.create.assert_not_called()

    def test_checkout_rejects_unknown_plan(self, mock_stripe):
        self.configure(mock_stripe)
        response = self.client.post(
            reverse("billing-checkout"), self.checkout_payload(plan="premium")
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_checkout_rejects_overlong_full_name(self, mock_stripe):
        self.configure(mock_stripe)
        response = self.client.post(
            reverse("billing-checkout"), self.checkout_payload(full_name="x" * 151)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_checkout_never_reuses_deactivated_privileged_accounts(self, mock_stripe):
        self.configure(mock_stripe)
        coach = User.objects.create_user(
            username="oldcoach",
            email="newclient@example.com",
            password="Pass12345!",
            is_active=False,
        )
        coach.groups.add(Group.objects.get(name=ROLE_COACH))

        response = self.client.post(reverse("billing-checkout"), self.checkout_payload())
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        coach.refresh_from_db()
        self.assertTrue(coach.groups.filter(name=ROLE_COACH).exists())
        self.assertTrue(coach.check_password("Pass12345!"))
        mock_stripe.checkout.Session.create.assert_not_called()


@mock.patch("billing.views.stripe")
class WebhookTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="pending@example.com",
            email="pending@example.com",
            password="Pass12345!",
            is_active=False,
        )
        cls.user.groups.add(Group.objects.get(name=ROLE_CLIENT))

    def post_webhook(self):
        return self.client.post(
            reverse("billing-webhook"),
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=bad",
        )

    def test_webhook_rejects_invalid_signature(self, mock_stripe):
        mock_stripe.Webhook.construct_event.side_effect = SignatureVerificationError(
            "signature mismatch", "t=1,v1=bad"
        )
        response = self.post_webhook()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_unknown_event_returns_200(self, mock_stripe):
        mock_stripe.Webhook.construct_event.return_value = webhook_event(
            "customer.created", {"id": "cus_123"}
        )
        response = self.post_webhook()
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_checkout_completed_activates_user_and_upserts_subscription(self, mock_stripe):
        mock_stripe.Webhook.construct_event.return_value = webhook_event(
            "checkout.session.completed",
            {
                "client_reference_id": str(self.user.id),
                "customer": "cus_123",
                "subscription": "sub_123",
            },
        )
        mock_stripe.Subscription.retrieve.return_value = stripe_subscription_payload(
            card={"brand": "visa", "last4": "4242"}
        )

        response = self.post_webhook()
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        subscription = Subscription.objects.get(user=self.user)
        self.assertEqual(subscription.stripe_subscription_id, "sub_123")
        self.assertEqual(subscription.plan, "full_support")
        self.assertEqual(subscription.interval, "monthly")
        self.assertEqual(subscription.status, "active")
        self.assertEqual(subscription.card_brand, "visa")
        self.assertEqual(subscription.card_last4, "4242")
        self.assertEqual(int(subscription.current_period_end.timestamp()), PERIOD_END)
        self.assertEqual(Customer.objects.get(user=self.user).stripe_customer_id, "cus_123")

        # Replayed events are idempotent: still one subscription, same state.
        second = self.post_webhook()
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(Subscription.objects.filter(user=self.user).count(), 1)

    def test_subscription_updated_syncs_fields(self, mock_stripe):
        Subscription.objects.create(
            user=self.user,
            stripe_subscription_id="sub_123",
            price_lookup_key="full_support_monthly",
            plan="full_support",
            interval="monthly",
            status="active",
        )
        mock_stripe.Webhook.construct_event.return_value = webhook_event(
            "customer.subscription.updated",
            stripe_subscription_payload(
                lookup_key="focus_lite_weekly", cancel_at_period_end=True
            ),
        )
        response = self.post_webhook()
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        subscription = Subscription.objects.get(user=self.user)
        self.assertEqual(subscription.plan, "focus_lite")
        self.assertEqual(subscription.interval, "weekly")
        self.assertEqual(subscription.price_lookup_key, "focus_lite_weekly")
        self.assertTrue(subscription.cancel_at_period_end)
        self.assertEqual(int(subscription.current_period_end.timestamp()), PERIOD_END)

    def test_subscription_deleted_marks_canceled(self, mock_stripe):
        Subscription.objects.create(
            user=self.user, stripe_subscription_id="sub_123", status="active"
        )
        mock_stripe.Webhook.construct_event.return_value = webhook_event(
            "customer.subscription.deleted",
            stripe_subscription_payload(sub_status="canceled"),
        )
        response = self.post_webhook()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        subscription = Subscription.objects.get(user=self.user)
        self.assertEqual(subscription.status, Subscription.STATUS_CANCELED)

    def test_stale_update_after_deletion_does_not_resurrect_subscription(self, mock_stripe):
        Subscription.objects.create(
            user=self.user,
            stripe_subscription_id="sub_123",
            status=Subscription.STATUS_CANCELED,
        )
        mock_stripe.Webhook.construct_event.return_value = webhook_event(
            "customer.subscription.updated",
            stripe_subscription_payload(sub_status="active"),
        )
        response = self.post_webhook()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Subscription.objects.get(user=self.user).status,
            Subscription.STATUS_CANCELED,
        )

    def test_payment_failed_sets_past_due_without_deactivating_user(self, mock_stripe):
        self.user.is_active = True
        self.user.save(update_fields=["is_active"])
        Subscription.objects.create(
            user=self.user, stripe_subscription_id="sub_123", status="active"
        )
        mock_stripe.Webhook.construct_event.return_value = webhook_event(
            "invoice.payment_failed",
            {"id": "in_123", "subscription": "sub_123"},
        )
        response = self.post_webhook()
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        subscription = Subscription.objects.get(user=self.user)
        self.assertEqual(subscription.status, Subscription.STATUS_PAST_DUE)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active, "payment failure must never deactivate the user")

    def test_payment_failed_reads_nested_subscription_details(self, mock_stripe):
        self.user.is_active = True
        self.user.save(update_fields=["is_active"])
        Subscription.objects.create(
            user=self.user, stripe_subscription_id="sub_123", status="active"
        )
        mock_stripe.Webhook.construct_event.return_value = webhook_event(
            "invoice.payment_failed",
            {
                "id": "in_123",
                "parent": {"subscription_details": {"subscription": "sub_123"}},
            },
        )
        response = self.post_webhook()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Subscription.objects.get(user=self.user).status, Subscription.STATUS_PAST_DUE
        )


class PortalAndSubscriptionTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.coach = User.objects.create_user(
            username="coach1", email="coach@example.com", password="Pass12345!"
        )
        cls.coach.groups.add(Group.objects.get(name=ROLE_COACH))
        cls.client_user = User.objects.create_user(
            username="client1", email="client@example.com", password="Pass12345!"
        )
        cls.client_user.groups.add(Group.objects.get(name=ROLE_CLIENT))
        cls.client_user.profile.assigned_coach = cls.coach
        cls.client_user.profile.save()

    def authenticate(self, username):
        response = self.client.post(
            reverse("login"), {"username": username, "password": "Pass12345!"}
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_portal_requires_authentication(self):
        response = self.client.post(reverse("billing-portal"), {"flow": None}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_portal_rejects_coach(self):
        self.authenticate("coach1")
        response = self.client.post(reverse("billing-portal"), {"flow": None}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_portal_without_billing_account_returns_404(self):
        self.authenticate("client1")
        response = self.client.post(reverse("billing-portal"), {"flow": None}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @mock.patch("billing.views.stripe")
    def test_portal_plain_session(self, mock_stripe):
        Customer.objects.create(user=self.client_user, stripe_customer_id="cus_123")
        mock_stripe.billing_portal.Session.create.return_value = {
            "url": "https://billing.stripe.com/p/session_123"
        }
        self.authenticate("client1")
        response = self.client.post(reverse("billing-portal"), {"flow": None}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["url"], "https://billing.stripe.com/p/session_123")
        kwargs = mock_stripe.billing_portal.Session.create.call_args.kwargs
        self.assertEqual(kwargs["customer"], "cus_123")
        self.assertNotIn("flow_data", kwargs)

    @mock.patch("billing.views.stripe")
    def test_portal_cancel_flow_deep_links_subscription(self, mock_stripe):
        Customer.objects.create(user=self.client_user, stripe_customer_id="cus_123")
        Subscription.objects.create(
            user=self.client_user, stripe_subscription_id="sub_123", status="active"
        )
        PortalConfiguration.objects.create(stripe_configuration_id="bpc_123")
        mock_stripe.billing_portal.Session.create.return_value = {
            "url": "https://billing.stripe.com/p/session_123"
        }
        self.authenticate("client1")
        response = self.client.post(
            reverse("billing-portal"), {"flow": "subscription_cancel"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        kwargs = mock_stripe.billing_portal.Session.create.call_args.kwargs
        self.assertEqual(kwargs["configuration"], "bpc_123")
        self.assertEqual(
            kwargs["flow_data"],
            {
                "type": "subscription_cancel",
                "subscription_cancel": {"subscription": "sub_123"},
            },
        )

    def test_portal_flow_without_subscription_returns_404(self):
        Customer.objects.create(user=self.client_user, stripe_customer_id="cus_123")
        self.authenticate("client1")
        response = self.client.post(
            reverse("billing-portal"), {"flow": "subscription_update"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_subscription_endpoint_returns_null_without_subscription(self):
        self.authenticate("client1")
        response = self.client.get(reverse("billing-subscription"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data)

    def test_subscription_endpoint_serializes_subscription(self):
        Subscription.objects.create(
            user=self.client_user,
            stripe_subscription_id="sub_123",
            price_lookup_key="full_support_monthly",
            plan="full_support",
            interval="monthly",
            status="active",
            card_brand="visa",
            card_last4="4242",
        )
        self.authenticate("client1")
        response = self.client.get(reverse("billing-subscription"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["plan_name"], "Full Support")
        self.assertEqual(response.data["amount"], 750)
        self.assertEqual(response.data["card_last4"], "4242")
