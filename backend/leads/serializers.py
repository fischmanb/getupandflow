from rest_framework import serializers

from .models import Lead, WaitlistEntry


class WaitlistEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = WaitlistEntry
        fields = ["id", "full_name", "email", "timezone", "plan", "interval", "created_at"]
        read_only_fields = ["id", "created_at"]


class LeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = ["id", "full_name", "email", "plan", "billing_period", "notes", "created_at"]
        read_only_fields = ["id", "created_at"]
