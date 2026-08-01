from django.contrib import admin

from .models import Escalation, EscalationTransition, ResolutionMethod


@admin.register(ResolutionMethod)
class ResolutionMethodAdmin(admin.ModelAdmin):
    """Bruce/leadership edit the resolution vocabulary here — no code change.
    Deactivate a method (uncheck `active`) to retire it from the close sheet
    while preserving it on historical audit rows."""

    list_display = ["name", "slug", "active", "sort_order"]
    list_editable = ["active", "sort_order"]
    prepopulated_fields = {"slug": ["name"]}
    ordering = ["sort_order", "name"]


class EscalationTransitionInline(admin.TabularInline):
    model = EscalationTransition
    extra = 0
    readonly_fields = [
        "actor", "from_status", "to_status", "note",
        "resolution_method", "resolution_note", "created_at",
    ]
    can_delete = False


@admin.register(Escalation)
class EscalationAdmin(admin.ModelAdmin):
    list_display = ["id", "trigger_id", "tier", "status", "confidence", "sla_deadline_at", "archived_at", "created_at"]
    list_filter = ["tier", "status"]
    search_fields = ["trigger_id", "client_ref", "session_ref"]
    readonly_fields = ["created_at", "updated_at", "resolved_by", "resolved_at", "archived_at"]
    inlines = [EscalationTransitionInline]


@admin.register(EscalationTransition)
class EscalationTransitionAdmin(admin.ModelAdmin):
    list_display = ["id", "escalation", "from_status", "to_status", "actor", "created_at"]
    list_filter = ["to_status"]
