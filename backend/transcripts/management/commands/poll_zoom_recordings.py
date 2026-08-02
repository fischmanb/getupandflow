"""Poll Zoom for recent cloud recordings and ingest their transcripts.

Webhook-independent path (Brian directive 2026-08-01 after Zoom dispatched
zero events across four correctly-configured test recordings): every run asks
Zoom's API for the account's recordings in a trailing window and pushes each
through the SAME idempotent ingest the webhook uses. unique(zoom_meeting_id)
makes this safe to run alongside a working webhook — whoever arrives first
stores; the other becomes a logged duplicate.
"""
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from planner import zoom
from transcripts.ingest import handle_recording_event

logger = logging.getLogger("transcripts")

# Trailing poll window. Two days covers Zoom's slowest observed transcript
# generation plus a weekend of cron outage without unbounded listing.
POLL_WINDOW_DAYS = 2


class Command(BaseCommand):
    help = "Poll Zoom cloud recordings (account-wide) and ingest transcripts."

    def handle(self, *args, **options):
        now = timezone.now()
        frm = (now - timedelta(days=POLL_WINDOW_DAYS)).date().isoformat()
        to = now.date().isoformat()
        try:
            payload = zoom.list_account_recordings(frm, to)
        except zoom.ZoomError as exc:
            self.stderr.write(f"Zoom listing failed: {exc}")
            return
        meetings = payload.get("meetings") or []
        stored = skipped = 0
        for meeting in meetings:
            # Synthesize the webhook body shape ingest already understands.
            body = {
                "event": "recording.completed",
                "payload": {"object": meeting},
                "download_token": None,  # S2S bearer auth is used instead
            }
            result = handle_recording_event(body, allow_retry=False)
            status = result.get("status")
            if status == "stored":
                stored += 1
                logger.info("Poller stored transcript for meeting %s", result.get("meeting_id"))
            else:
                skipped += 1
        self.stdout.write(f"poll_zoom_recordings: {len(meetings)} meetings, {stored} stored, {skipped} skipped/duplicate")
