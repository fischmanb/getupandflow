from django.conf import settings
from django.db import models

from .constants import STATUS_CHOICES, STATUS_OPEN


class Escalation(models.Model):
    """A clinical-crisis flag raised by the grading engine, queued for the
    clinical lead. Ordering is severity-first: tier ASC (1 = most severe),
    then soonest SLA deadline, then highest confidence.
    """

    # The flagged client. Nullable FK for pre-linkage ingests (the grader may
    # not yet know the platform user); client_ref carries the grader's own
    # free-text handle either way.
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="escalations",
    )
    client_ref = models.CharField(max_length=200, blank=True)
    session_ref = models.CharField(max_length=200, blank=True)

    # Doctrine, mirrored from triggers.yaml. tier: 1|2|3, 1 = most severe.
    trigger_id = models.CharField(max_length=100)
    tier = models.PositiveSmallIntegerField()
    confidence = models.FloatField()
    # List of evidence spans, e.g. [{"quote": "...", "start": 12, "end": 40}].
    evidence = models.JSONField(default=list, blank=True)

    # Server-recomputed from tier + received_at at ingest (server math wins).
    sla_deadline_at = models.DateTimeField()

    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_OPEN)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Queue order: tier ASC, deadline ASC, confidence DESC.
        ordering = ["tier", "sla_deadline_at", "-confidence"]
        indexes = [
            models.Index(fields=["status", "tier", "sla_deadline_at"]),
        ]

    def __str__(self):
        return f"Escalation<{self.trigger_id} T{self.tier} {self.status}>"


class EscalationTransition(models.Model):
    """One audited lifecycle transition. Every status change writes a row —
    including false_positive, which is retained, never deleted."""

    escalation = models.ForeignKey(
        Escalation,
        on_delete=models.CASCADE,
        related_name="transitions",
    )
    # Nullable: the creation row is authored by the system (no human actor).
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="escalation_transitions",
    )
    from_status = models.CharField(max_length=32, blank=True)
    to_status = models.CharField(max_length=32)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"Transition<{self.escalation_id} {self.from_status}->{self.to_status}>"
