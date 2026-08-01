from django.conf import settings
from django.db import models

from .constants import GRADING_PENDING, GRADING_STATUS_CHOICES
from .storage import select_transcript_storage


class Transcript(models.Model):
    """One coaching-session transcript, ingested from a Zoom cloud recording.

    Retained even if the event or the people are later deleted (all three FKs
    SET_NULL): a graded transcript is a clinical record, not calendar chrome.
    occurred_at is the MEETING's start — never ingest time — so downstream
    grading orders sessions by when they actually happened.
    """

    # Source event (the calendar entry whose Zoom meeting produced this).
    event = models.ForeignKey(
        "planner.Event",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transcripts",
    )
    # The client the session was for (from the event's client) and the coach
    # who ran it (the client's assigned coach at ingest time).
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="session_transcripts",
    )
    coach = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="coached_transcripts",
    )

    # The Zoom meeting id (matches Event.zoom_meeting_id). Indexed and unique:
    # one transcript per meeting — makes redelivered webhooks idempotent.
    zoom_meeting_id = models.BigIntegerField(unique=True)

    # The meeting's start datetime (parsed from the recording payload), NOT
    # now(). This is the clinical occurrence time.
    occurred_at = models.DateTimeField()

    vtt_file = models.FileField(upload_to="transcripts/", storage=select_transcript_storage)
    # Speaker-tagged plain text extracted from the VTT (for grading).
    plain_text = models.TextField(blank=True)
    duration_s = models.PositiveIntegerField(default=0)

    grading_status = models.CharField(
        max_length=16,
        choices=GRADING_STATUS_CHOICES,
        default=GRADING_PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"Transcript<meeting={self.zoom_meeting_id} {self.occurred_at:%Y-%m-%d}>"
