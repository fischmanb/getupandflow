from django.contrib import admin

from .models import Lead


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "plan", "billing_period", "created_at")
    list_filter = ("plan", "billing_period", "created_at")
    search_fields = ("full_name", "email", "notes")
    readonly_fields = ("created_at",)
