from django.contrib import admin

from .models import Customer, PortalConfiguration, Subscription


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ["user", "stripe_customer_id", "created_at"]
    search_fields = ["user__username", "user__email", "stripe_customer_id"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "plan",
        "interval",
        "status",
        "cancel_at_period_end",
        "current_period_end",
    ]
    list_filter = ["plan", "interval", "status", "cancel_at_period_end"]
    search_fields = ["user__username", "user__email", "stripe_subscription_id"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(PortalConfiguration)
class PortalConfigurationAdmin(admin.ModelAdmin):
    list_display = ["stripe_configuration_id", "updated_at"]
