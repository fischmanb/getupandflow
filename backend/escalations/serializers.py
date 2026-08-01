from django.utils import timezone
from rest_framework import serializers

from .constants import ALLOWED_TRANSITIONS, STATUS_CHOICES, TERMINAL_STATUSES
from .loader import VALID_TIERS
from .models import Escalation, EscalationTransition
from .presentation import client_display_name, client_initials, trigger_label


class IngestSerializer(serializers.Serializer):
    """The grading-engine contract. sla_deadline_at is NOT accepted from the
    client — the server recomputes it from tier + received_at (server math wins).
    """

    trigger_id = serializers.CharField(max_length=100)
    tier = serializers.IntegerField(min_value=1)
    confidence = serializers.FloatField(min_value=0.0, max_value=1.0)
    client_ref = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    session_ref = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    client_id = serializers.IntegerField(required=False, allow_null=True)
    evidence = serializers.ListField(child=serializers.JSONField(), required=False, default=list)

    def validate_tier(self, value):
        if value not in VALID_TIERS:
            raise serializers.ValidationError(f"tier must be one of {sorted(VALID_TIERS)} (1 = most severe).")
        return value


class TransitionSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", default=None, read_only=True)

    class Meta:
        model = EscalationTransition
        fields = ["id", "from_status", "to_status", "note", "actor_username", "created_at"]


class EscalationListSerializer(serializers.ModelSerializer):
    trigger_label = serializers.SerializerMethodField()
    client_initials = serializers.SerializerMethodField()
    breached = serializers.SerializerMethodField()
    seconds_remaining = serializers.SerializerMethodField()

    class Meta:
        model = Escalation
        fields = [
            "id", "trigger_id", "trigger_label", "tier", "confidence",
            "client_initials", "session_ref", "status", "sla_deadline_at",
            "breached", "seconds_remaining", "created_at", "updated_at",
        ]

    def get_trigger_label(self, obj):
        return trigger_label(obj.trigger_id)

    def get_client_initials(self, obj):
        return client_initials(obj)

    def get_breached(self, obj):
        return timezone.now() >= obj.sla_deadline_at

    def get_seconds_remaining(self, obj):
        # Computed live, never stored. Negative once breached.
        return int((obj.sla_deadline_at - timezone.now()).total_seconds())


class EscalationDetailSerializer(EscalationListSerializer):
    """Detail adds the shoulder-surf-gated fields (full name, evidence spans)
    and the audit trail. The list view deliberately omits these."""

    client_name = serializers.SerializerMethodField()
    transitions = TransitionSerializer(many=True, read_only=True)
    allowed_next_states = serializers.SerializerMethodField()

    class Meta(EscalationListSerializer.Meta):
        fields = EscalationListSerializer.Meta.fields + [
            "client_ref", "client_name", "evidence", "transitions", "allowed_next_states",
        ]

    def get_client_name(self, obj):
        return client_display_name(obj)

    def get_allowed_next_states(self, obj):
        return sorted(ALLOWED_TRANSITIONS.get(obj.status, frozenset()))
