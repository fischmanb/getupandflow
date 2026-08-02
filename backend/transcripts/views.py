import json
import logging
import time

from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from datetime import timezone as dt_timezone
from drf_spectacular.utils import extend_schema

from . import webhook
from .constants import (
    FEED_SIGNATURE_HEADER,
    ZOOM_EVENT_URL_VALIDATION,
    ZOOM_SIGNATURE_HEADER,
    ZOOM_SIGNATURE_TIMESTAMP_HEADER,
)
from .feed_auth import feed_signature_valid
from .ingest import handle_recording_event
from .models import Transcript
from .pagination import TranscriptFeedPagination
from .serializers import TranscriptFeedSerializer

logger = logging.getLogger("transcripts")


class ZoomWebhookView(APIView):
    """POST /api/zoom/webhook/ — Zoom event receiver.

    Two jobs: answer the one-time endpoint-URL validation challenge, and accept
    recording events after verifying their v0 signature. Recording events are
    always acknowledged 200 once authentic (so Zoom stops retrying) even when we
    choose not to store — consent revoked, no matching event, transcript not
    ready. Storage/consent/idempotency all live in ingest.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(request=None, responses=None)
    def post(self, request):
        raw_body = request.body
        try:
            body = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except (ValueError, UnicodeDecodeError):
            return Response({"detail": "Invalid JSON."}, status=status.HTTP_400_BAD_REQUEST)

        event_type = body.get("event")

        # Endpoint-URL validation challenge: echo plainToken + its HMAC.
        if event_type == ZOOM_EVENT_URL_VALIDATION:
            plain_token = (body.get("payload") or {}).get("plainToken")
            answer = webhook.validation_response(plain_token)
            if answer is None:
                logger.error("Zoom URL validation failed: ZOOM_WEBHOOK_SECRET_TOKEN unset.")
                return Response(
                    {"detail": "Webhook secret not configured."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            return Response(answer, status=status.HTTP_200_OK)

        # Every other event must carry a valid v0 signature.
        signature = request.headers.get(ZOOM_SIGNATURE_HEADER, "")
        ts = request.headers.get(ZOOM_SIGNATURE_TIMESTAMP_HEADER, "")
        if not webhook.signature_valid(raw_body, ts, signature, now_ts=int(time.time())):
            return Response(
                {"detail": "Invalid or missing signature."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        result = handle_recording_event(body)
        return Response({"received": True, **result}, status=status.HTTP_200_OK)


class TranscriptFeedView(generics.ListAPIView):
    """GET /api/transcripts/feed/?since=<iso> — outbound pull for sorel.

    HMAC of the raw query string in X-GUAF-Signature (shared machine secret).
    Ordered by created_at; paginated. `since` is an EXCLUSIVE high-water mark on
    created_at (pass the created_at of the last transcript you ingested).
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = TranscriptFeedSerializer
    pagination_class = TranscriptFeedPagination

    @extend_schema(responses=TranscriptFeedSerializer(many=True))
    def list(self, request, *args, **kwargs):
        query_string = request.META.get("QUERY_STRING", "")
        signature = request.headers.get(FEED_SIGNATURE_HEADER, "")
        if not feed_signature_valid(query_string, signature):
            return Response(
                {"detail": "Invalid or missing signature."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        queryset = Transcript.objects.all().order_by("created_at", "id")
        raw_since = self.request.query_params.get("since")
        if raw_since:
            since = parse_datetime(raw_since)
            if since is None:
                raise ValidationError({"since": "Enter a valid ISO 8601 datetime."})
            if timezone.is_naive(since):
                since = timezone.make_aware(since, dt_timezone.utc)
            queryset = queryset.filter(created_at__gt=since)
        return queryset


class TranscriptPollView(APIView):
    """POST /api/transcripts/poll/ — HMAC-authenticated on-demand poll.

    Runs the same account-wide recording sweep as the poll_zoom_recordings
    management command, synchronously, and returns the counts. Auth: the feed's
    HMAC scheme over the literal body "poll" (constant, replay-safe enough for
    an idempotent read-and-ingest trigger). Exists so operators (and sorel) can
    force an ingest sweep without waiting on cron or Zoom webhooks.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        signature = request.headers.get(FEED_SIGNATURE_HEADER, "")
        if not feed_signature_valid("poll", signature):
            return Response({"detail": "Invalid signature."}, status=status.HTTP_401_UNAUTHORIZED)
        from datetime import timedelta
        from planner import zoom
        from .management.commands.poll_zoom_recordings import POLL_WINDOW_DAYS
        now = timezone.now()
        frm = (now - timedelta(days=POLL_WINDOW_DAYS)).date().isoformat()
        to = now.date().isoformat()
        try:
            payload = zoom.list_account_recordings(frm, to)
        except zoom.ZoomError as exc:
            logger.warning("On-demand poll: Zoom listing failed: %s", exc)
            return Response({"detail": f"Zoom listing failed ({exc.status_code})."},
                            status=status.HTTP_502_BAD_GATEWAY)
        meetings = payload.get("meetings") or []
        results = []
        for meeting in meetings:
            body = {"event": "recording.completed", "payload": {"object": meeting}, "download_token": None}
            results.append(handle_recording_event(body, allow_retry=False))
        stored = sum(1 for r in results if r.get("status") == "stored")
        return Response({"meetings": len(meetings), "stored": stored,
                         "statuses": [r.get("status") for r in results]})
