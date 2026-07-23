from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from billing.models import Subscription

from .constants import ROLE_CLIENT, ROLE_COACH
from .models import ClientOnboarding, UserProfile

PAID_STATUSES = (Subscription.STATUS_ACTIVE, Subscription.STATUS_PAST_DUE)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "assigned_coach", "phone_number", "zoom_user_email", "created_at")
    search_fields = ("user__username", "user__email", "assigned_coach__username")


class CoachAssignmentQueueEntry(UserProfile):
    """Active paid clients still waiting for a coach (proxy for the admin queue)."""

    class Meta:
        proxy = True
        verbose_name = "Coach assignment queue entry"
        verbose_name_plural = "Coach assignment queue"


@admin.register(CoachAssignmentQueueEntry)
class CoachAssignmentQueueAdmin(admin.ModelAdmin):
    """Paid, active clients with no coach yet. Assigning a coach here saves the
    profile, which triggers the coach-assigned email (notifications.signals)."""

    list_display = ("client_email", "client_name", "plan", "paid_at", "hours_since_payment")
    fields = ("client_email", "client_name", "plan", "paid_at", "assigned_coach")
    readonly_fields = ("client_email", "client_name", "plan", "paid_at")
    search_fields = ("user__username", "user__email")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .filter(
                assigned_coach__isnull=True,
                user__is_active=True,
                user__groups__name=ROLE_CLIENT,
                user__billing_subscription__status__in=PAID_STATUSES,
            )
            .select_related("user", "user__billing_subscription")
            .order_by("user__billing_subscription__created_at")
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "assigned_coach":
            kwargs["queryset"] = (
                db_field.related_model.objects.filter(groups__name=ROLE_COACH)
                .distinct()
                .order_by("first_name", "last_name", "username")
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description="Client")
    def client_name(self, obj):
        return obj.user.get_full_name() or obj.user.username

    @admin.display(description="Email")
    def client_email(self, obj):
        return obj.user.email

    @admin.display(description="Plan")
    def plan(self, obj):
        subscription = obj.user.billing_subscription
        plan_name = subscription.get_plan_display() or subscription.price_lookup_key
        return f"{plan_name} ({subscription.get_interval_display()})" if subscription.interval else plan_name

    @admin.display(description="Paid at", ordering="user__billing_subscription__created_at")
    def paid_at(self, obj):
        return obj.user.billing_subscription.created_at

    @admin.display(description="Hours since payment")
    def hours_since_payment(self, obj):
        elapsed = timezone.now() - obj.user.billing_subscription.created_at
        hours = elapsed.total_seconds() / 3600
        if hours > 24:
            return format_html('<strong style="color:#b91c1c;">{}h</strong>', int(hours))
        return f"{int(hours)}h"


@admin.register(ClientOnboarding)
class ClientOnboardingAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "timezone",
        "morning_window",
        "evening_window",
        "contact_method",
        "contact_number",
        "completed_at",
    )
    search_fields = ("user__username", "user__email")
    readonly_fields = ("completed_at", "created_at", "updated_at")
