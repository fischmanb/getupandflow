import hashlib
import hmac
import json
import time
from datetime import datetime, timezone as dt_timezone
from unittest import mock

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.constants import ROLE_CLIENT, ROLE_COACH
from planner.models import Event, EventCategory

from . import ingest, vtt
from .constants import (
    ZOOM_EVENT_RECORDING_COMPLETED,
    ZOOM_EVENT_TRANSCRIPT_COMPLETED,
    ZOOM_EVENT_URL_VALIDATION,
)
from .models import Transcript
from .webhook import _hmac_hex

WEBHOOK_SECRET = "test-webhook-secret-token"
FEED_SECRET = "test-shared-machine-secret"
MEETING_ID = 555000111
MEETING_START = "2026-08-01T15:00:00Z"

SAMPLE_VTT = (
    "WEBVTT\n"
    "\n"
    "1\n"
    "00:00:01.000 --> 00:00:04.000\n"
    "Coach Casey: How was your week?\n"
    "\n"
    "2\n"
    "00:00:05.000 --> 00:00:09.500\n"
    "Client Jordan: Pretty good, stayed on track.\n"
)


def _recording_body(event=ZOOM_EVENT_RECORDING_COMPLETED, *, meeting_id=MEETING_ID,
                    include_transcript=True, download_token="dl-token"):
    recording_files = [
        {"id": "mp4-1", "file_type": "MP4", "download_url": "https://zoom.us/rec/mp4"},
    ]
    if include_transcript:
        recording_files.append(
            {
                "id": "vtt-1",
                "file_type": "TRANSCRIPT",
                "file_extension": "VTT",
                "download_url": "https://zoom.us/rec/transcript.vtt",
                "status": "completed",
            }
        )
    body = {
        "event": event,
        "payload": {
            "account_id": "acct-1",
            "object": {
                "id": meeting_id,
                "uuid": "uuid-1",
                "topic": "Coaching",
                "start_time": MEETING_START,
                "duration": 30,
                "recording_files": recording_files,
            },
        },
    }
    if download_token is not None:
        body["download_token"] = download_token
    return body


class TranscriptTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.coach_group = Group.objects.get(name=ROLE_COACH)
        cls.client_group = Group.objects.get(name=ROLE_CLIENT)

        cls.coach = User.objects.create_user(username="tcoach", password="pw", first_name="Casey")
        cls.coach.groups.add(cls.coach_group)
        cls.coach.profile.zoom_user_email = "coach@zoom.example.com"
        cls.coach.profile.save()

        cls.client_user = User.objects.create_user(username="tclient", password="pw", first_name="Jordan")
        cls.client_user.groups.add(cls.client_group)
        cls.client_user.profile.assigned_coach = cls.coach
        cls.client_user.profile.save()

        cls.category = EventCategory.objects.create(name="Coaching", color="sky", client=cls.client_user)
        cls.event = Event.objects.create(
            title="Weekly Check-in",
            event_date="2026-08-01",
            start_time="15:00:00",
            end_time="15:30:00",
            category=cls.category,
            client=cls.client_user,
            zoom_meeting_id=MEETING_ID,
        )

    def setUp(self):
        self.api = APIClient()


# ── VTT parsing (unit) ──────────────────────────────────────────────────────
class VttParseTests(TestCase):
    def test_speaker_tagged_text_and_duration(self):
        text, duration = vtt.parse(SAMPLE_VTT)
        self.assertEqual(
            text,
            "Coach Casey: How was your week?\nClient Jordan: Pretty good, stayed on track.",
        )
        self.assertEqual(duration, 9)  # last cue ends at 9.5s -> int 9

    def test_voice_tag_form(self):
        raw = (
            "WEBVTT\n\n1\n00:00:00.000 --> 00:00:02.000\n"
            "<v Coach>Let's begin.</v>\n"
        )
        text, duration = vtt.parse(raw)
        self.assertEqual(text, "Coach: Let's begin.")
        self.assertEqual(duration, 2)

    def test_empty_vtt(self):
        text, duration = vtt.parse("WEBVTT\n\n")
        self.assertEqual(text, "")
        self.assertEqual(duration, 0)


# ── Webhook: URL validation challenge ───────────────────────────────────────
@mock.patch.dict("os.environ", {"ZOOM_WEBHOOK_SECRET_TOKEN": WEBHOOK_SECRET})
class WebhookValidationTests(TranscriptTestBase):
    def test_validation_challenge_returns_encrypted_token(self):
        plain = "abc123plain"
        body = {"event": ZOOM_EVENT_URL_VALIDATION, "payload": {"plainToken": plain}}
        resp = self.api.post(reverse("zoom-webhook"), data=json.dumps(body),
                             content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["plainToken"], plain)
        expected = _hmac_hex(WEBHOOK_SECRET, plain.encode())
        self.assertEqual(resp.json()["encryptedToken"], expected)

    def test_validation_without_secret_is_503(self):
        with mock.patch.dict("os.environ", {"ZOOM_WEBHOOK_SECRET_TOKEN": ""}):
            body = {"event": ZOOM_EVENT_URL_VALIDATION, "payload": {"plainToken": "x"}}
            resp = self.api.post(reverse("zoom-webhook"), data=json.dumps(body),
                                 content_type="application/json")
        self.assertEqual(resp.status_code, 503)


# ── Webhook: signature + recording.completed -> Transcript ──────────────────
@mock.patch.dict("os.environ", {"ZOOM_WEBHOOK_SECRET_TOKEN": WEBHOOK_SECRET})
class WebhookIngestTests(TranscriptTestBase):
    def _sign(self, raw, ts):
        message = f"v0:{ts}:{raw}".encode()
        return "v0=" + _hmac_hex(WEBHOOK_SECRET, message)

    def _post(self, body, *, ts=None, signature=None):
        raw = json.dumps(body)
        ts = str(int(time.time())) if ts is None else ts
        sig = self._sign(raw, ts) if signature is None else signature
        return self.api.post(
            reverse("zoom-webhook"),
            data=raw,
            content_type="application/json",
            HTTP_X_ZM_SIGNATURE=sig,
            HTTP_X_ZM_REQUEST_TIMESTAMP=ts,
        )

    @mock.patch("planner.zoom.download_recording_file", return_value=SAMPLE_VTT.encode())
    def test_recording_completed_creates_transcript(self, download):
        resp = self._post(_recording_body())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "stored")

        transcript = Transcript.objects.get()
        self.assertEqual(transcript.zoom_meeting_id, MEETING_ID)
        self.assertEqual(transcript.client, self.client_user)
        self.assertEqual(transcript.coach, self.coach)
        self.assertEqual(transcript.event, self.event)
        # occurred_at is the MEETING start, never now().
        self.assertEqual(
            transcript.occurred_at,
            datetime(2026, 8, 1, 15, 0, tzinfo=dt_timezone.utc),
        )
        self.assertEqual(transcript.duration_s, 9)
        self.assertIn("Coach Casey: How was your week?", transcript.plain_text)
        # Raw VTT written to storage and round-trips.
        transcript.vtt_file.open("rb")
        self.assertEqual(transcript.vtt_file.read(), SAMPLE_VTT.encode())
        transcript.vtt_file.close()
        # Download authorized with the webhook's download token.
        self.assertEqual(download.call_args.kwargs["download_token"], "dl-token")

    @mock.patch("planner.zoom.download_recording_file", return_value=SAMPLE_VTT.encode())
    def test_bad_signature_rejected(self, download):
        resp = self._post(_recording_body(), signature="v0=deadbeef")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(Transcript.objects.count(), 0)
        download.assert_not_called()

    @mock.patch("planner.zoom.download_recording_file", return_value=SAMPLE_VTT.encode())
    def test_missing_signature_rejected(self, download):
        raw = json.dumps(_recording_body())
        resp = self.api.post(reverse("zoom-webhook"), data=raw, content_type="application/json")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(Transcript.objects.count(), 0)

    @mock.patch("planner.zoom.download_recording_file", return_value=SAMPLE_VTT.encode())
    def test_stale_timestamp_rejected(self, download):
        old_ts = str(int(time.time()) - 3600)  # 1h old, beyond the 5-min skew
        resp = self._post(_recording_body(), ts=old_ts)
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(Transcript.objects.count(), 0)

    @mock.patch("planner.zoom.download_recording_file", return_value=SAMPLE_VTT.encode())
    def test_redelivery_is_idempotent(self, download):
        self.assertEqual(self._post(_recording_body()).json()["status"], "stored")
        self.assertEqual(self._post(_recording_body()).json()["status"], "duplicate")
        self.assertEqual(Transcript.objects.count(), 1)

    @mock.patch("planner.zoom.download_recording_file", return_value=SAMPLE_VTT.encode())
    def test_adhoc_no_matching_event_stored_unlinked(self, download):
        """Brian ruling 2026-08-01: ad-hoc meetings capture too — Zoom's native
        participant recording-acknowledgement is the consent mechanism when no
        GUAF event linkage exists. Stored with event/client/coach NULL."""
        resp = self._post(_recording_body(meeting_id=999999))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "stored")
        t = Transcript.objects.get(zoom_meeting_id=999999)
        self.assertIsNone(t.event)
        self.assertIsNone(t.client)
        self.assertIsNone(t.coach)
        self.assertIsNotNone(t.occurred_at)

    @mock.patch("planner.zoom.download_recording_file", return_value=SAMPLE_VTT.encode())
    def test_consent_revoked_acknowledged_not_stored(self, download):
        profile = self.client_user.profile
        profile.recording_consent = False
        profile.save()
        resp = self._post(_recording_body())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "consent_revoked")
        self.assertEqual(Transcript.objects.count(), 0)
        download.assert_not_called()

    @mock.patch("transcripts.ingest.schedule_deferred_retry")
    @mock.patch("planner.zoom.download_recording_file")
    def test_download_404_defers_poll_once(self, download, schedule):
        download.side_effect = ingest.zoom.ZoomError("not ready", status_code=404)
        resp = self._post(_recording_body())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "deferred")
        schedule.assert_called_once()
        self.assertEqual(Transcript.objects.count(), 0)

    @mock.patch("planner.zoom.download_recording_file")
    def test_retry_disabled_does_not_reschedule(self, download):
        # The retry itself (allow_retry=False) must not loop on a persistent 404.
        download.side_effect = ingest.zoom.ZoomError("not ready", status_code=404)
        with mock.patch("transcripts.ingest.schedule_deferred_retry") as schedule:
            result = ingest.handle_recording_event(_recording_body(), allow_retry=False)
        self.assertEqual(result["status"], "download_failed")
        schedule.assert_not_called()

    @mock.patch("planner.zoom.download_recording_file", return_value=SAMPLE_VTT.encode())
    def test_transcript_arrives_in_later_event(self, download):
        # recording.completed with no TRANSCRIPT file yet -> nothing stored.
        early = self._post(_recording_body(include_transcript=False))
        self.assertEqual(early.json()["status"], "no_transcript_file")
        self.assertEqual(Transcript.objects.count(), 0)
        # The follow-up transcript_completed event carries it.
        late = self._post(_recording_body(event=ZOOM_EVENT_TRANSCRIPT_COMPLETED))
        self.assertEqual(late.json()["status"], "stored")
        self.assertEqual(Transcript.objects.count(), 1)


# ── Feed for sorel ──────────────────────────────────────────────────────────
@mock.patch.dict("os.environ", {"GUAF_ESCALATION_INGEST_SECRET": FEED_SECRET})
class FeedTests(TranscriptTestBase):
    def _make_transcript(self, meeting_id, occurred_at):
        return Transcript.objects.create(
            event=self.event,
            client=self.client_user,
            coach=self.coach,
            zoom_meeting_id=meeting_id,
            occurred_at=occurred_at,
            plain_text=f"Coach: session {meeting_id}",
            duration_s=100,
        )

    def _sign(self, query_string):
        return hmac.new(FEED_SECRET.encode(), query_string.encode(), hashlib.sha256).hexdigest()

    def _get(self, query_string="", *, signature=None):
        sig = self._sign(query_string) if signature is None else signature
        url = reverse("transcript-feed")
        if query_string:
            url = f"{url}?{query_string}"
        return self.api.get(url, HTTP_X_GUAF_SIGNATURE=sig)

    def test_valid_signature_returns_transcripts(self):
        self._make_transcript(1, datetime(2026, 8, 1, 15, 0, tzinfo=dt_timezone.utc))
        resp = self._get("")
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertEqual(len(results), 1)
        row = results[0]
        self.assertEqual(row["zoom_meeting_id"], 1)
        self.assertEqual(row["client_id"], self.client_user.id)
        self.assertEqual(row["coach_id"], self.coach.id)
        self.assertEqual(row["grading_status"], "pending")
        self.assertIn("plain_text", row)

    def test_bad_signature_rejected(self):
        self._make_transcript(1, datetime(2026, 8, 1, 15, 0, tzinfo=dt_timezone.utc))
        resp = self._get("", signature="nope")
        self.assertEqual(resp.status_code, 401)

    def test_missing_signature_rejected(self):
        resp = self.api.get(reverse("transcript-feed"))
        self.assertEqual(resp.status_code, 401)

    def test_since_filters_exclusive_high_water_mark(self):
        early = self._make_transcript(1, datetime(2026, 8, 1, 12, 0, tzinfo=dt_timezone.utc))
        late = self._make_transcript(2, datetime(2026, 8, 2, 12, 0, tzinfo=dt_timezone.utc))
        # created_at is auto; force a known ordering via update.
        Transcript.objects.filter(pk=early.pk).update(
            created_at=datetime(2026, 8, 1, 0, 0, tzinfo=dt_timezone.utc)
        )
        Transcript.objects.filter(pk=late.pk).update(
            created_at=datetime(2026, 8, 5, 0, 0, tzinfo=dt_timezone.utc)
        )
        qs = "since=2026-08-03T00:00:00Z"
        resp = self._get(qs)
        self.assertEqual(resp.status_code, 200)
        ids = [r["zoom_meeting_id"] for r in resp.json()["results"]]
        self.assertEqual(ids, [2])

    def test_invalid_since_is_400(self):
        qs = "since=not-a-date"
        resp = self._get(qs)
        self.assertEqual(resp.status_code, 400)


# ── Storage selection ───────────────────────────────────────────────────────
class StorageSelectionTests(TestCase):
    def test_uses_r2_when_configured(self):
        from . import storage

        fake_r2 = object()
        with mock.patch("transcripts.storage.is_configured", return_value=True), \
                mock.patch("transcripts.storage.R2MediaStorage", return_value=fake_r2):
            self.assertIs(storage.select_transcript_storage(), fake_r2)

    def test_falls_back_to_local_without_r2(self):
        from django.core.files.storage import FileSystemStorage

        from . import storage

        with mock.patch("transcripts.storage.is_configured", return_value=False):
            self.assertIsInstance(storage.select_transcript_storage(), FileSystemStorage)


class PollZoomRecordingsTests(TestCase):
    """Webhook-independent poller: same ingest, same idempotency."""

    @mock.patch("planner.zoom.download_recording_file", return_value=SAMPLE_VTT.encode())
    @mock.patch("planner.zoom.list_account_recordings")
    def test_poller_ingests_and_is_idempotent(self, listing, download):
        from django.core.management import call_command
        from io import StringIO
        listing.return_value = {"meetings": [_recording_body(meeting_id=555000111)["payload"]["object"]]}
        out = StringIO()
        call_command("poll_zoom_recordings", stdout=out)
        self.assertEqual(Transcript.objects.filter(zoom_meeting_id=555000111).count(), 1)
        self.assertIn("1 stored", out.getvalue())
        out2 = StringIO()
        call_command("poll_zoom_recordings", stdout=out2)
        self.assertEqual(Transcript.objects.filter(zoom_meeting_id=555000111).count(), 1)
        self.assertIn("1 skipped", out2.getvalue())

    @mock.patch("planner.zoom.list_account_recordings", side_effect=Exception)
    def test_poller_listing_failure_is_contained(self, listing):
        from django.core.management import call_command
        listing.side_effect = __import__("planner.zoom", fromlist=["ZoomError"]).ZoomError("down", status_code=500)
        from io import StringIO
        err = StringIO()
        call_command("poll_zoom_recordings", stderr=err)
        self.assertIn("Zoom listing failed", err.getvalue())
        self.assertEqual(Transcript.objects.count(), 0)
