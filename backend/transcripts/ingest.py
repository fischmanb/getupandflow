"""Turn a Zoom recording webhook into a stored, consent-gated Transcript row.

Flow (all failure-soft — a webhook is always acknowledged 200 so Zoom stops
retrying; we log and move on):

  recording.completed / recording.transcript_completed
    -> match Event by zoom_meeting_id      (no match -> log, skip)
    -> consent gate on the event's client  (revoked -> log, skip)
    -> find the TRANSCRIPT (VTT) file       (not present yet -> skip; a later
                                             recording.transcript_completed
                                             event will carry it)
    -> download via S2S/download token
         404 -> file not materialized yet: poll ONCE after a short delay
    -> parse VTT (speaker-tagged text + duration)
    -> store raw VTT to R2 + create Transcript (occurred_at = MEETING start)

Idempotent on zoom_meeting_id (unique): redelivered webhooks and the deferred
retry cannot create a second row.
"""

import logging
import threading
import time
from datetime import datetime, timezone as dt_timezone

from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from planner import zoom
from planner.models import Event

from . import vtt
from .constants import (
    TRANSCRIPT_RETRY_DELAY_SECONDS,
    ZOOM_EVENT_RECORDING_COMPLETED,
    ZOOM_EVENT_TRANSCRIPT_COMPLETED,
    ZOOM_TRANSCRIPT_FILE_TYPE,
)
from .consent import client_has_recording_consent
from .models import Transcript

logger = logging.getLogger("transcripts")

RECORDING_EVENTS = frozenset({ZOOM_EVENT_RECORDING_COMPLETED, ZOOM_EVENT_TRANSCRIPT_COMPLETED})

# HTTP 404 from the download endpoint = the transcript is listed but not yet
# generated; the one place we branch on a specific status.
_HTTP_NOT_FOUND = 404


def handle_recording_event(body, *, allow_retry=True):
    """Process a recording.* webhook body. Returns a small status dict for
    logging/tests; never raises for expected conditions."""
    event_type = body.get("event")
    if event_type not in RECORDING_EVENTS:
        return {"status": "ignored_event", "event": event_type}

    obj = (body.get("payload") or {}).get("object") or {}
    raw_meeting_id = obj.get("id")
    try:
        meeting_id = int(raw_meeting_id)
    except (TypeError, ValueError):
        logger.warning("Zoom recording webhook missing/invalid meeting id: %r", raw_meeting_id)
        return {"status": "no_meeting_id"}

    if Transcript.objects.filter(zoom_meeting_id=meeting_id).exists():
        return {"status": "duplicate", "meeting_id": meeting_id}

    event = Event.objects.select_related("client", "client__profile", "client__profile__assigned_coach").filter(
        zoom_meeting_id=meeting_id
    ).first()
    if event is None:
        # Ad-hoc meetings capture too (Brian ruling 2026-08-01): Zoom's native
        # recording notice — every participant must acknowledge before joining
        # a recorded call — is the consent mechanism for meetings with no GUAF
        # event linkage. Stored unlinked (event/client/coach NULL); linkage can
        # be attached later.
        logger.info("Zoom recording for meeting %s has no matching event; storing unlinked (ad-hoc).", meeting_id)
        client = None
    else:
        client = event.client
    if client is not None and not client_has_recording_consent(client):
        logger.info(
            "Recording consent absent/revoked for client %s (meeting %s); acknowledged, not stored.",
            getattr(client, "id", None),
            meeting_id,
        )
        return {"status": "consent_revoked", "meeting_id": meeting_id}

    transcript_file = _find_transcript_file(obj)
    if transcript_file is None:
        logger.info(
            "Meeting %s recording has no %s file yet; awaiting transcript_completed.",
            meeting_id,
            ZOOM_TRANSCRIPT_FILE_TYPE,
        )
        return {"status": "no_transcript_file", "meeting_id": meeting_id}

    download_url = transcript_file.get("download_url")
    if not download_url:
        logger.warning("Transcript file for meeting %s has no download_url.", meeting_id)
        return {"status": "no_download_url", "meeting_id": meeting_id}

    download_token = body.get("download_token")
    try:
        vtt_bytes = zoom.download_recording_file(download_url, download_token=download_token)
    except zoom.ZoomError as exc:
        if exc.status_code == _HTTP_NOT_FOUND and allow_retry:
            logger.info(
                "Transcript for meeting %s not ready (404); scheduling one retry in %ss.",
                meeting_id,
                TRANSCRIPT_RETRY_DELAY_SECONDS,
            )
            schedule_deferred_retry(body)
            return {"status": "deferred", "meeting_id": meeting_id}
        logger.warning("Transcript download failed for meeting %s: %s", meeting_id, exc)
        return {"status": "download_failed", "meeting_id": meeting_id}

    plain_text, duration_s = vtt.parse(vtt_bytes)
    occurred_at = _meeting_start(obj, event)
    if occurred_at is None:
        logger.warning("Meeting %s: no start_time in payload and no linked event; not stored.", meeting_id)
        return {"status": "no_start_time", "meeting_id": meeting_id}
    coach = _coach_for(client) if client is not None else None

    try:
        with transaction.atomic():
            transcript = Transcript.objects.create(
                event=event,
                client=client,
                coach=coach,
                zoom_meeting_id=meeting_id,
                occurred_at=occurred_at,
                plain_text=plain_text,
                duration_s=duration_s,
            )
            transcript.vtt_file.save(f"meeting-{meeting_id}.vtt", ContentFile(vtt_bytes), save=True)
    except IntegrityError:
        # Concurrent redelivery/retry won the unique(zoom_meeting_id) race.
        logger.info("Transcript for meeting %s already stored (race); skipping.", meeting_id)
        return {"status": "duplicate", "meeting_id": meeting_id}

    logger.info("Stored transcript %s for meeting %s (%ss).", transcript.id, meeting_id, duration_s)
    return {"status": "stored", "meeting_id": meeting_id, "transcript_id": transcript.id}


def _find_transcript_file(obj):
    for recording_file in obj.get("recording_files") or []:
        if (recording_file.get("file_type") or "").upper() == ZOOM_TRANSCRIPT_FILE_TYPE:
            return recording_file
    return None


def _meeting_start(obj, event):
    """The MEETING's start datetime — never now(). Prefer the payload's
    start_time; fall back to the linked event's scheduled start."""
    raw_start = obj.get("start_time")
    if raw_start:
        parsed = parse_datetime(raw_start)
        if parsed is not None:
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed, dt_timezone.utc)
            return parsed
    if event is None:
        # Unlinked ad-hoc meeting with no payload start_time: nothing honest to
        # anchor occurred_at to (never now()); caller skips with a logged status.
        return None
    naive = datetime.combine(event.event_date, event.start_time)
    return timezone.make_aware(naive, timezone.get_current_timezone())


def _coach_for(client):
    profile = getattr(client, "profile", None)
    return profile.assigned_coach if profile else None


def schedule_deferred_retry(body):
    """Poll-once fallback: after a short delay, re-run ingest for this webhook
    with retries disabled. A single daemon thread — no new queue or daemon
    process. Patched out in tests."""

    def _run():
        time.sleep(TRANSCRIPT_RETRY_DELAY_SECONDS)
        try:
            handle_recording_event(body, allow_retry=False)
        except Exception:
            logger.exception("Deferred transcript retry crashed for body %r", body.get("event"))

    meeting_id = ((body.get("payload") or {}).get("object") or {}).get("id")
    thread = threading.Thread(
        target=_run,
        name=f"zoom-transcript-retry-{meeting_id}",
        daemon=True,
    )
    thread.start()
