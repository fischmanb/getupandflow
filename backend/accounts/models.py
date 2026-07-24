import zoneinfo
from functools import lru_cache

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .constants import ROLE_ADMIN, ROLE_CLIENT, ROLE_COACH
from .storage import select_photo_storage


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    assigned_coach = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="coached_clients",
    )
    phone_number = models.CharField(max_length=30, blank=True)
    zoom_user_email = models.EmailField(null=True, blank=True)
    bio = models.TextField(blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    photo = models.ImageField(upload_to="coach-photos/", null=True, blank=True, storage=select_photo_storage)
    # Recorded at signup; written via queryset update() because profile
    # save() enforces the client-must-have-a-coach rule (see ClientOnboarding).
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    terms_version = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        user_role = get_user_role(self.user)
        if self.assigned_coach and not self.assigned_coach.groups.filter(name=ROLE_COACH).exists():
            raise ValidationError({"assigned_coach": "Assigned coach must belong to the Coach group."})
        if self.assigned_coach and user_role != ROLE_CLIENT:
            raise ValidationError({"assigned_coach": "Only clients can be assigned to a coach."})
        if user_role == ROLE_CLIENT and not self.assigned_coach:
            raise ValidationError({"assigned_coach": "Each client must be assigned exactly one coach."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"Profile<{self.user.username}>"


class ClientOnboarding(models.Model):
    """Self-serve client onboarding answers, collected at /app/onboarding.

    Kept separate from UserProfile on purpose: profile saves are blocked for
    clients without an assigned coach (the exactly-one-coach rule), and
    onboarding happens precisely in that pre-assignment window.
    """

    # Legacy 2-hour blocks: rows saved before the hourly change keep these
    # values; they stay valid choices so display and PATCH tolerate them
    # without a data migration. The onboarding form only offers hourly.
    LEGACY_MORNING_WINDOW_CHOICES = [
        ("6-8am", "6:00–8:00 am"),
        ("8-10am", "8:00–10:00 am"),
        ("10am-12pm", "10:00 am–12:00 pm"),
    ]
    LEGACY_EVENING_WINDOW_CHOICES = [
        ("4-6pm", "4:00–6:00 pm"),
        ("6-8pm", "6:00–8:00 pm"),
        ("8-10pm", "8:00–10:00 pm"),
    ]
    HOURLY_MORNING_WINDOW_CHOICES = [
        ("6-7am", "6:00–7:00 am"),
        ("7-8am", "7:00–8:00 am"),
        ("8-9am", "8:00–9:00 am"),
        ("9-10am", "9:00–10:00 am"),
        ("10-11am", "10:00–11:00 am"),
        ("11am-12pm", "11:00 am–12:00 pm"),
    ]
    HOURLY_EVENING_WINDOW_CHOICES = [
        ("4-5pm", "4:00–5:00 pm"),
        ("5-6pm", "5:00–6:00 pm"),
        ("6-7pm", "6:00–7:00 pm"),
        ("7-8pm", "7:00–8:00 pm"),
        ("8-9pm", "8:00–9:00 pm"),
        ("9-10pm", "9:00–10:00 pm"),
    ]
    MORNING_WINDOW_CHOICES = HOURLY_MORNING_WINDOW_CHOICES + LEGACY_MORNING_WINDOW_CHOICES
    EVENING_WINDOW_CHOICES = HOURLY_EVENING_WINDOW_CHOICES + LEGACY_EVENING_WINDOW_CHOICES
    CONTACT_WHATSAPP = "whatsapp"
    CONTACT_SMS = "sms"
    CONTACT_METHOD_CHOICES = [
        (CONTACT_WHATSAPP, "WhatsApp"),
        (CONTACT_SMS, "SMS"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="client_onboarding")
    timezone = models.CharField(max_length=64)
    morning_window = models.CharField(max_length=20, choices=MORNING_WINDOW_CHOICES)
    evening_window = models.CharField(max_length=20, choices=EVENING_WINDOW_CHOICES)
    contact_method = models.CharField(max_length=10, choices=CONTACT_METHOD_CHOICES)
    contact_number = models.CharField(max_length=30)
    help_topics = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @staticmethod
    @lru_cache(maxsize=1)
    def available_timezones():
        return zoneinfo.available_timezones()

    def save(self, *args, **kwargs):
        if self.completed_at is None:
            self.completed_at = timezone.now()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"Onboarding<{self.user.username}>"


def get_user_role(user):
    if user.is_superuser:
        return ROLE_ADMIN
    group = user.groups.order_by("name").first()
    return group.name if group else None
