from django.urls import path

from .views import (
    BillingConfigView,
    CheckoutView,
    PortalView,
    StripeWebhookView,
    SubscriptionView,
)

urlpatterns = [
    path("config/", BillingConfigView.as_view(), name="billing-config"),
    path("checkout/", CheckoutView.as_view(), name="billing-checkout"),
    path("portal/", PortalView.as_view(), name="billing-portal"),
    path("subscription/", SubscriptionView.as_view(), name="billing-subscription"),
    path("webhook/", StripeWebhookView.as_view(), name="billing-webhook"),
]
