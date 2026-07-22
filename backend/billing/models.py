from django.contrib.auth.models import User
from django.db import models

from .catalog import INTERVAL_CHOICES, PLAN_CHOICES


class Customer(models.Model):
    """Maps an app user to their Stripe Customer."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="billing_customer")
    stripe_customer_id = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} ({self.stripe_customer_id})"


class Subscription(models.Model):
    """Local cache of a user's Stripe subscription, synced by webhooks."""

    STATUS_ACTIVE = "active"
    STATUS_PAST_DUE = "past_due"
    STATUS_CANCELED = "canceled"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="billing_subscription")
    stripe_subscription_id = models.CharField(max_length=255, unique=True)
    price_lookup_key = models.CharField(max_length=100, blank=True)
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, blank=True)
    interval = models.CharField(max_length=10, choices=INTERVAL_CHOICES, blank=True)
    status = models.CharField(max_length=32, default=STATUS_ACTIVE)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    card_brand = models.CharField(max_length=20, blank=True)
    card_last4 = models.CharField(max_length=4, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}: {self.price_lookup_key or 'unknown plan'} ({self.status})"


class PortalConfiguration(models.Model):
    """Singleton storing the Stripe Customer Portal configuration id.

    Created/updated by the ``ensure_stripe_catalog`` management command.
    """

    stripe_configuration_id = models.CharField(max_length=255, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Stripe portal configuration"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return self.stripe_configuration_id or "(not configured)"
