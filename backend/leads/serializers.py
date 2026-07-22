from rest_framework import serializers

from .models import Lead


class LeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = ["id", "full_name", "email", "plan", "billing_period", "notes", "created_at"]
        read_only_fields = ["id", "created_at"]
