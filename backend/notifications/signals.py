"""Coach-assignment notification.

Every assignment path (Django admin queue, admin site, in-app admin user
management) ends in a UserProfile.save() that sets assigned_coach, so the
transition is detected here centrally: the first time a paid, active client
gets a coach, they receive the coach-assigned email. Manually created clients
(no billing subscription) are not emailed -- this flow belongs to self-serve
signups only.
"""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from accounts.constants import ROLE_CLIENT
from accounts.models import UserProfile
from billing.models import Subscription

from .emails import send_coach_assigned_email

PAID_STATUSES = (Subscription.STATUS_ACTIVE, Subscription.STATUS_PAST_DUE)


# No sender= filter: proxy models (the admin assignment queue) dispatch
# signals with the proxy class as sender, which a sender=UserProfile
# registration would silently miss. The isinstance gate covers both.
@receiver(pre_save)
def capture_previous_coach(sender, instance, **kwargs):
    if not isinstance(instance, UserProfile):
        return
    previous = None
    if instance.pk:
        previous = (
            UserProfile.objects.filter(pk=instance.pk)
            .values_list("assigned_coach_id", flat=True)
            .first()
        )
    instance._previous_assigned_coach_id = previous


@receiver(post_save)
def notify_coach_assignment(sender, instance, created, **kwargs):
    if not isinstance(instance, UserProfile):
        return
    if getattr(instance, "_previous_assigned_coach_id", None) or not instance.assigned_coach_id:
        return
    user = instance.user
    if not user.is_active or not user.email:
        return
    if not user.groups.filter(name=ROLE_CLIENT).exists():
        return
    if not Subscription.objects.filter(user=user, status__in=PAID_STATUSES).exists():
        return
    send_coach_assigned_email(user, instance.assigned_coach)
