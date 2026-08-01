from django.conf import settings
from django.db import models

from .constants import STATUS_CHOICES, STATUS_OPEN


class ResolutionMethod(models.Model):
    """Bruce's editable vocabulary for how an escalation was resolved. Seeded by
    a data migration, then owned by leadership through Django admin — the queue
    reads whichever rows are `active`, so the vocabulary changes without code.
    """

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120, unique=True)
    active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


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

    # Resolution — set when the escalation is closed (resolved / false_positive /
    # escalated_to_clinical). The audit trail (EscalationTransition) also carries
    # the method/note at the moment of each close; these mirror the CURRENT
    # closing state and are cleared on reopen.
    resolution_method = models.ForeignKey(
        ResolutionMethod,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="escalations",
    )
    resolution_note = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="escalations_resolved",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    # Set when a closing status is entered; cleared on reopen. The queue's
    # default view excludes archived rows; the Archive view shows only them.
    archived_at = models.DateTimeField(null=True, blank=True)

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
    # The resolution captured at a closing transition (null for lifecycle moves
    # that don't close, and for the system-authored creation row). This is the
    # durable audit — it survives a later reopen even after the Escalation's own
    # resolution fields are cleared.
    resolution_method = models.ForeignKey(
        ResolutionMethod,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transitions",
    )
    resolution_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"Transition<{self.escalation_id} {self.from_status}->{self.to_status}>"
