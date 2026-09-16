from django.db import models


class WaitlistEntry(models.Model):
    """Someone who wanted to buy but sits outside current coach coverage."""

    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    timezone = models.CharField(max_length=64)
    plan = models.CharField(max_length=20, blank=True)
    interval = models.CharField(max_length=10, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} ({self.timezone})"


class Lead(models.Model):
    PLAN_FULL_SUPPORT = "full_support"
    PLAN_FOCUS_LITE = "focus_lite"
    PLAN_CHOICES = [
        (PLAN_FULL_SUPPORT, "Full Support"),
        (PLAN_FOCUS_LITE, "Focus Lite"),
    ]

    BILLING_MONTHLY = "monthly"
    BILLING_WEEKLY = "weekly"
    BILLING_CHOICES = [
        (BILLING_MONTHLY, "Monthly"),
        (BILLING_WEEKLY, "Weekly"),
    ]

    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default=PLAN_FULL_SUPPORT)
    billing_period = models.CharField(max_length=10, choices=BILLING_CHOICES, default=BILLING_MONTHLY)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name} <{self.email}> ({self.get_plan_display()})"
