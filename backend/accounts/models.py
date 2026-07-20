from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models

from .constants import ROLE_ADMIN, ROLE_CLIENT, ROLE_COACH


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


def get_user_role(user):
    if user.is_superuser:
        return ROLE_ADMIN
    group = user.groups.order_by("name").first()
    return group.name if group else None
