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
    STATUS_FILTER_GROUPS,
    STATUS_OPEN,
    allowed_next_states,
)
from .delivery import deliver_escalation
from .hmac_auth import signature_valid
from .loader import TriggerSpecError, load_triggers
from .models import Escalation, EscalationTransition
from .permissions import LeadershipPermission
from .serializers import (
    EscalationDetailSerializer,
    EscalationListSerializer,
    IngestSerializer,
    TransitionSerializer,
)
from .sla import compute_sla_deadline

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
    (open | in_review | closed)."""

    permission_classes = [LeadershipPermission]
    serializer_class = EscalationListSerializer

    def get_queryset(self):
        queryset = Escalation.objects.select_related("client").all()
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

    Body: {to_status, note?}. Rejects any move not in the lifecycle graph with
    400 + the allowed next states. Every accepted move writes an audit row.
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

        from_status = escalation.status
        with transaction.atomic():
            escalation.status = to_status
            escalation.save(update_fields=["status", "updated_at"])
            EscalationTransition.objects.create(
                escalation=escalation,
                actor=request.user,
                from_status=from_status,
                to_status=to_status,
                note=note,
            )

        return Response(EscalationDetailSerializer(escalation).data, status=status.HTTP_200_OK)
