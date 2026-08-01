import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .constants import (
    ALLOWED_TRANSITIONS,
    RESOLUTION_METHOD_OTHER,
    STATUS_FILTER_GROUPS,
    STATUS_IN_REVIEW,
    STATUS_OPEN,
    TERMINAL_STATUSES,
    allowed_next_states,
)
from .delivery import deliver_escalation
from .hmac_auth import signature_valid
from .loader import TriggerSpecError, load_triggers
from .models import Escalation, EscalationTransition, ResolutionMethod
from .permissions import LeadershipPermission
from .serializers import (
    EscalationDetailSerializer,
    EscalationListSerializer,
    IngestSerializer,
    ResolutionMethodSerializer,
    TransitionSerializer,
)
from .sla import compute_sla_deadline

# Query-param truthy values for ?archived=.
_TRUTHY = {"1", "true", "yes", "on"}


def _active_methods_payload():
    """Active resolution methods as the 400 body and the /methods/ endpoint
    both render them — slug + name, in leadership's sort order."""
    methods = ResolutionMethod.objects.filter(active=True)
    return ResolutionMethodSerializer(methods, many=True).data

logger = logging.getLogger("escalations")
User = get_user_model()


class EscalationIngestView(APIView):
    """POST /api/escalations/ingest/ — the grading-engine integration contract.

    HMAC-SHA256 of the raw body (X-GUAF-Signature) gates entry. The server
    recomputes sla_deadline_at from tier + receipt time — the payload cannot set
    it. Delivery (ntfy always; Tier-1 email too) fires on_commit.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        raw_body = request.body
        signature = request.headers.get("X-GUAF-Signature", "")
        if not signature_valid(raw_body, signature):
            return Response(
                {"detail": "Invalid or missing signature."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Fail closed: doctrine must load before we admit any clinical flag.
        try:
            spec = load_triggers()
        except TriggerSpecError:
            logger.error("Escalation ingest blocked: triggers.yaml failed to load", exc_info=True)
            return Response(
                {"detail": "Escalation doctrine unavailable; ingest is closed."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        serializer = IngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        client = None
        client_id = data.get("client_id")
        if client_id is not None:
            client = User.objects.filter(pk=client_id).first()
            if client is None:
                raise ValidationError({"client_id": "No user with this id."})

        received_at = timezone.now()
        deadline = compute_sla_deadline(received_at, data["tier"], spec)

        with transaction.atomic():
            escalation = Escalation.objects.create(
                client=client,
                client_ref=data.get("client_ref", ""),
                session_ref=data.get("session_ref", ""),
                trigger_id=data["trigger_id"],
                tier=data["tier"],
                confidence=data["confidence"],
                evidence=data.get("evidence", []),
                sla_deadline_at=deadline,
                status=STATUS_OPEN,
            )
            # System-authored creation row (no human actor).
            EscalationTransition.objects.create(
                escalation=escalation,
                actor=None,
                from_status="",
                to_status=STATUS_OPEN,
                note="Ingested from grading engine.",
            )
            # Same transaction, delivery on commit: the row is durable before
            # any push/email fires, and a delivery error never rolls it back.
            transaction.on_commit(lambda: deliver_escalation(escalation))

        return Response(
            EscalationDetailSerializer(escalation).data,
            status=status.HTTP_201_CREATED,
        )


class EscalationListView(generics.ListAPIView):
    """GET /api/escalations/ — leadership queue, ordered tier ASC,
    sla_deadline_at ASC, confidence DESC (the model's default ordering).
    Optional ?status= accepts a lifecycle state OR a filter group
    (open | in_review | closed). By default archived (closed) rows are
    excluded; ?archived=true returns only archived rows (the Archive view)."""

    permission_classes = [LeadershipPermission]
    serializer_class = EscalationListSerializer

    def get_queryset(self):
        queryset = Escalation.objects.select_related(
            "client", "resolution_method", "resolved_by"
        ).all()

        archived = self.request.query_params.get("archived", "").lower() in _TRUTHY
        if archived:
            queryset = queryset.filter(archived_at__isnull=False)
        else:
            queryset = queryset.filter(archived_at__isnull=True)

        raw_status = self.request.query_params.get("status")
        if raw_status:
            if raw_status in STATUS_FILTER_GROUPS:
                queryset = queryset.filter(status__in=STATUS_FILTER_GROUPS[raw_status])
            else:
                queryset = queryset.filter(status=raw_status)
        return queryset


class EscalationDetailView(generics.RetrieveAPIView):
    """GET /api/escalations/{id}/ — full record incl. name, evidence, audit."""

    permission_classes = [LeadershipPermission]
    serializer_class = EscalationDetailSerializer
    queryset = Escalation.objects.select_related("client").prefetch_related(
        "transitions", "transitions__actor"
    )


class EscalationTransitionView(APIView):
    """POST /api/escalations/{id}/transition/ — advance the lifecycle.

    Body: {to_status, note?, resolution_method?, resolution_note?}. Rejects any
    move not in the lifecycle graph with 400 + the allowed next states. Closing
    moves (resolved / false_positive / escalated_to_clinical) REQUIRE a
    resolution_method (slug); "other" additionally requires a resolution_note.
    A close stamps resolution + resolved_by/at + archived_at on the escalation
    and copies the resolution onto the audit row. Every accepted move writes an
    audit row.
    """

    permission_classes = [LeadershipPermission]

    def post(self, request, pk):
        escalation = generics.get_object_or_404(Escalation, pk=pk)
        to_status = request.data.get("to_status")
        note = request.data.get("note", "") or ""

        if not to_status:
            return Response(
                {"detail": "to_status is required.",
                 "allowed_next_states": allowed_next_states(escalation.status)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        allowed = ALLOWED_TRANSITIONS.get(escalation.status, frozenset())
        if to_status not in allowed:
            return Response(
                {"detail": f"Cannot move from {escalation.status} to {to_status}.",
                 "allowed_next_states": sorted(allowed)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Closing moves must carry a resolution method (and a note for "other").
        method = None
        resolution_note = request.data.get("resolution_note", "") or ""
        if to_status in TERMINAL_STATUSES:
            method_slug = request.data.get("resolution_method")
            if method_slug:
                method = ResolutionMethod.objects.filter(
                    slug=method_slug, active=True
                ).first()
            if method is None:
                return Response(
                    {"detail": "A resolution method is required to close this "
                               "escalation. Choose one of the methods listed.",
                     "resolution_methods": _active_methods_payload()},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if method.slug == RESOLUTION_METHOD_OTHER and not resolution_note.strip():
                return Response(
                    {"detail": "A note is required when the resolution method is "
                               "“Other”."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        from_status = escalation.status
        with transaction.atomic():
            escalation.status = to_status
            update_fields = ["status", "updated_at"]
            if to_status in TERMINAL_STATUSES:
                now = timezone.now()
                escalation.resolution_method = method
                escalation.resolution_note = resolution_note
                escalation.resolved_by = request.user
                escalation.resolved_at = now
                escalation.archived_at = now
                update_fields += [
                    "resolution_method", "resolution_note",
                    "resolved_by", "resolved_at", "archived_at",
                ]
            escalation.save(update_fields=update_fields)
            EscalationTransition.objects.create(
                escalation=escalation,
                actor=request.user,
                from_status=from_status,
                to_status=to_status,
                note=note,
                resolution_method=method,
                resolution_note=resolution_note if to_status in TERMINAL_STATUSES else "",
            )

        return Response(EscalationDetailSerializer(escalation).data, status=status.HTTP_200_OK)


class EscalationReopenView(APIView):
    """POST /api/escalations/{id}/reopen/ — leadership-only reopen of an
    archived escalation back into review.

    Only an archived (closed) escalation can be reopened; the move is audited
    like any other transition. The escalation's own resolution fields are
    cleared (it is no longer resolved) but the audit trail keeps the resolution
    that was recorded at close.
    """

    permission_classes = [LeadershipPermission]

    def post(self, request, pk):
        escalation = generics.get_object_or_404(Escalation, pk=pk)
        if escalation.archived_at is None:
            return Response(
                {"detail": "Only an archived escalation can be reopened."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        note = request.data.get("note", "") or ""
        from_status = escalation.status
        with transaction.atomic():
            escalation.status = STATUS_IN_REVIEW
            escalation.archived_at = None
            escalation.resolution_method = None
            escalation.resolution_note = ""
            escalation.resolved_by = None
            escalation.resolved_at = None
            escalation.save(update_fields=[
                "status", "archived_at", "resolution_method",
                "resolution_note", "resolved_by", "resolved_at", "updated_at",
            ])
            EscalationTransition.objects.create(
                escalation=escalation,
                actor=request.user,
                from_status=from_status,
                to_status=STATUS_IN_REVIEW,
                note=note or "Reopened for further review.",
            )

        return Response(EscalationDetailSerializer(escalation).data, status=status.HTTP_200_OK)


class ResolutionMethodListView(generics.ListAPIView):
    """GET /api/escalations/methods/ — the active resolution vocabulary for the
    close sheet, in leadership's sort order."""

    permission_classes = [LeadershipPermission]
    serializer_class = ResolutionMethodSerializer

    def get_queryset(self):
        return ResolutionMethod.objects.filter(active=True)
