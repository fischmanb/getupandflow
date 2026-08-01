from rest_framework import serializers

from .models import Transcript


class TranscriptFeedSerializer(serializers.ModelSerializer):
    """The contract sorel pulls: transcript metadata plus the extracted,
    speaker-tagged plain text. The raw VTT is not inlined — feed consumers work
    from plain_text; the file lives in R2."""

    client_id = serializers.IntegerField(read_only=True)
    coach_id = serializers.IntegerField(read_only=True)
    event_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Transcript
        fields = [
            "id",
            "event_id",
            "client_id",
            "coach_id",
            "zoom_meeting_id",
            "occurred_at",
            "duration_s",
            "grading_status",
            "plain_text",
            "created_at",
        ]
        read_only_fields = fields
