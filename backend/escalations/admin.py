from django.contrib import admin

from .models import Escalation, EscalationTransition


class EscalationTransitionInline(admin.TabularInline):
    model = EscalationTransition
    extra = 0
    readonly_fields = ["actor", "from_status", "to_status", "note", "created_at"]
    can_delete = False


@admin.register(Escalation)
class EscalationAdmin(admin.ModelAdmin):
    list_display = ["id", "trigger_id", "tier", "status", "confidence", "sla_deadline_at", "created_at"]
    list_filter = ["tier", "status"]
    search_fields = ["trigger_id", "client_ref", "session_ref"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [EscalationTransitionInline]


@admin.register(EscalationTransition)
class EscalationTransitionAdmin(admin.ModelAdmin):
    list_display = ["id", "escalation", "from_status", "to_status", "actor", "created_at"]
    list_filter = ["to_status"]
