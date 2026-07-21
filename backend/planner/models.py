from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models

from accounts.constants import ROLE_CLIENT
from accounts.models import get_user_role


class EventCategory(models.Model):
    PRESET_COLORS = [
        ("rose", "Rose"),
        ("orange", "Orange"),
        ("amber", "Amber"),
        ("emerald", "Emerald"),
        ("sky", "Sky"),
        ("indigo", "Indigo"),
    ]

    client = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="event_categories",
    )
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=20, choices=PRESET_COLORS, default="emerald")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["client", "name"], name="unique_event_category_name_per_client"),
        ]

    def clean(self):
        if not self.client_id:
            return
        if get_user_role(self.client) != ROLE_CLIENT:
            raise ValidationError({"client": "Categories must belong to a client user."})
        if not self.client.profile.assigned_coach_id:
            raise ValidationError({"client": "Each client must have exactly one coach assigned."})

    def __str__(self):
        if not self.client_id:
            return self.name
        return f"{self.client.username}:{self.name}"


class ClientOwnedModel(models.Model):
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name="%(class)ss")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def validate_client(self):
        if get_user_role(self.client) != ROLE_CLIENT:
            raise ValidationError({"client": "Selected user must belong to the Client group."})
        if not self.client.profile.assigned_coach_id:
            raise ValidationError({"client": "Each client must have exactly one coach assigned."})


class Event(ClientOwnedModel):
    class RecurrenceChoices(models.TextChoices):
        NONE = "none", "Does not repeat"
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"

    title = models.CharField(max_length=255)
    event_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    location = models.CharField(max_length=255, blank=True)
    meeting_link = models.URLField(max_length=500, blank=True)
    zoom_meeting_id = models.BigIntegerField(null=True, blank=True)
    description = models.TextField(blank=True)
    category = models.ForeignKey(EventCategory, on_delete=models.PROTECT, related_name="events")
    recurrence_type = models.CharField(
        max_length=20,
        choices=RecurrenceChoices.choices,
        default=RecurrenceChoices.NONE,
    )
    recurrence_until = models.DateField(null=True, blank=True)
    client_name = models.CharField(max_length=255, editable=False)

    class Meta:
        ordering = ["event_date", "start_time", "title"]

    def clean(self):
        self.validate_client()
        if self.end_time <= self.start_time:
            raise ValidationError({"end_time": "End time must be after start time."})
        if self.category_id and self.category.client_id != self.client_id:
            raise ValidationError({"category": "Event category must belong to the same client as the event."})
        if self.recurrence_type == self.RecurrenceChoices.NONE:
            self.recurrence_until = None
        elif not self.recurrence_until:
            raise ValidationError({"recurrence_until": "Recurring events must include an end date."})
        elif self.recurrence_until < self.event_date:
            raise ValidationError({"recurrence_until": "Recurring event end date must be on or after the start date."})

    def save(self, *args, **kwargs):
        self.client_name = self.client.get_full_name() or self.client.username
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class Task(ClientOwnedModel):
    PRIORITY_HIGH = "high"
    PRIORITY_MEDIUM = "medium"
    PRIORITY_LOW = "low"
    PRIORITY_CHOICES = [
        (PRIORITY_HIGH, "High"),
        (PRIORITY_MEDIUM, "Medium"),
        (PRIORITY_LOW, "Low"),
    ]

    title = models.CharField(max_length=255)
    deadline = models.DateTimeField()
    description = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM)
    # Manual rank within a priority bucket; lower sorts first. Drag-and-drop writes this.
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "deadline", "title"]

    def clean(self):
        self.validate_client()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.title
