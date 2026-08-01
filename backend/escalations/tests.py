import hashlib
import hmac
import json
from datetime import datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.constants import ROLE_ADMIN, ROLE_CLIENT
from .constants import (
    DEFAULT_RESOLUTION_METHODS,
    STATUS_ACKNOWLEDGED,
    STATUS_ESCALATED_TO_CLINICAL,
    STATUS_FALSE_POSITIVE,
    STATUS_IN_REVIEW,
    STATUS_OPEN,
    STATUS_RESOLVED,
    seed_resolution_methods,
)
from .models import Escalation, EscalationTransition, ResolutionMethod
from .sla import business_hours_deadline, compute_sla_deadline

ET = ZoneInfo("America/New_York")
SECRET = "test-ingest-secret"


def sign(secret, raw_bytes):
    return hmac.new(secret.encode(), raw_bytes, hashlib.sha256).hexdigest()


def make_escalation(**kwargs):
    defaults = dict(
        trigger_id="suicidal_thought",
        tier=1,
        confidence=0.9,
        evidence=[],
        sla_deadline_at=timezone.now() + timedelta(hours=12),
        status=STATUS_OPEN,
    )
    defaults.update(kwargs)
    return Escalation.objects.create(**defaults)


# ── SLA business-hours math ─────────────────────────────────────────────────
class BusinessHoursMathTests(TestCase):
    def test_friday_evening_tier2_due_tuesday(self):
        received = datetime(2026, 8, 7, 20, 0, tzinfo=ET)  # Friday 8pm ET
        deadline = compute_sla_deadline(received, 2).astimezone(ET)
        self.assertEqual(deadline, datetime(2026, 8, 11, 0, 0, tzinfo=ET))  # Tuesday 00:00
        self.assertEqual(deadline.strftime("%A"), "Tuesday")

    def test_friday_evening_tier3_skips_weekend(self):
        received = datetime(2026, 8, 7, 20, 0, tzinfo=ET)
        deadline = compute_sla_deadline(received, 3).astimezone(ET)
        # 72 business hours = 3 business days from Monday 00:00 -> Thursday 00:00
        self.assertEqual(deadline, datetime(2026, 8, 13, 0, 0, tzinfo=ET))

    def test_tier1_is_calendar_any_day(self):
        received = datetime(2026, 8, 8, 9, 0, tzinfo=ET)  # Saturday
        deadline = compute_sla_deadline(received, 1)
        self.assertEqual(deadline, received + timedelta(hours=12))

    def test_weekend_supplies_no_hours(self):
        # A Saturday-received tier2 accrues nothing until Monday.
        received = datetime(2026, 8, 8, 12, 0, tzinfo=ET)  # Saturday
        deadline = business_hours_deadline(received, 24, "America/New_York").astimezone(ET)
        self.assertEqual(deadline, datetime(2026, 8, 11, 0, 0, tzinfo=ET))  # Tuesday 00:00


# ── HMAC ingest ─────────────────────────────────────────────────────────────
@mock.patch("escalations.hmac_auth.get_ingest_secret", return_value=SECRET)
@mock.patch("escalations.views.deliver_escalation")
class IngestHmacTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("escalation-ingest")
        self.payload = {
            "trigger_id": "suicidal_thought",
            "tier": 1,
            "confidence": 0.87,
            "client_ref": "grader-abc",
            "session_ref": "sess-1",
            "evidence": [{"quote": "I want to die", "start": 0, "end": 13}],
        }

    def _post(self, signature=None, body=None):
        raw = json.dumps(body or self.payload)
        headers = {}
        if signature is not None:
            headers["HTTP_X_GUAF_SIGNATURE"] = signature
        return self.client.post(self.url, data=raw, content_type="application/json", **headers)

    def test_valid_signature_accepted(self, _deliver, _secret):
        raw = json.dumps(self.payload)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(
                self.url, data=raw, content_type="application/json",
                HTTP_X_GUAF_SIGNATURE=sign(SECRET, raw.encode()),
            )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Escalation.objects.count(), 1)
        esc = Escalation.objects.get()
        self.assertEqual(esc.status, STATUS_OPEN)
        # System-authored creation audit row exists.
        self.assertTrue(esc.transitions.filter(to_status=STATUS_OPEN, actor__isnull=True).exists())
        _deliver.assert_called_once()

    def test_bad_signature_rejected(self, _deliver, _secret):
        resp = self._post(signature="deadbeef")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(Escalation.objects.count(), 0)
        _deliver.assert_not_called()

    def test_missing_signature_rejected(self, _deliver, _secret):
        resp = self._post(signature=None)
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(Escalation.objects.count(), 0)

    def test_sha256_prefix_tolerated(self, _deliver, _secret):
        raw = json.dumps(self.payload)
        resp = self.client.post(
            self.url, data=raw, content_type="application/json",
            HTTP_X_GUAF_SIGNATURE="sha256=" + sign(SECRET, raw.encode()),
        )
        self.assertEqual(resp.status_code, 201)

    def test_server_recomputes_deadline(self, _deliver, _secret):
        # Payload tries to inject a bogus deadline; server must ignore it.
        body = dict(self.payload, tier=1, sla_deadline_at="2000-01-01T00:00:00Z")
        raw = json.dumps(body)
        before = timezone.now()
        resp = self.client.post(
            self.url, data=raw, content_type="application/json",
            HTTP_X_GUAF_SIGNATURE=sign(SECRET, raw.encode()),
        )
        self.assertEqual(resp.status_code, 201)
        esc = Escalation.objects.get()
        # Tier 1 = received + 12h calendar, near now, NOT the injected year 2000.
        self.assertGreater(esc.sla_deadline_at, before)
        self.assertLess(esc.sla_deadline_at, before + timedelta(hours=12, minutes=1))


@mock.patch("escalations.hmac_auth.get_ingest_secret", return_value="")
class IngestFailClosedTests(TestCase):
    def test_no_secret_rejects_all(self, _secret):
        client = APIClient()
        raw = json.dumps({"trigger_id": "x", "tier": 1, "confidence": 0.5})
        resp = client.post(
            reverse("escalation-ingest"), data=raw, content_type="application/json",
            HTTP_X_GUAF_SIGNATURE=sign("anything", raw.encode()),
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(Escalation.objects.count(), 0)


# ── Delivery: push always, Tier-1 email too ─────────────────────────────────
class DeliveryTests(TestCase):
    @mock.patch("escalations.delivery.send_tier1_clinical_email")
    @mock.patch("escalations.delivery.send_escalation_push")
    def test_tier1_fires_push_and_email(self, push, email):
        from .delivery import deliver_escalation
        deliver_escalation(make_escalation(tier=1))
        push.assert_called_once()
        email.assert_called_once()

    @mock.patch("escalations.delivery.send_tier1_clinical_email")
    @mock.patch("escalations.delivery.send_escalation_push")
    def test_tier2_fires_push_only(self, push, email):
        from .delivery import deliver_escalation
        deliver_escalation(make_escalation(tier=2))
        push.assert_called_once()
        email.assert_not_called()

    @mock.patch("escalations.delivery.send_escalation_push", side_effect=RuntimeError("ntfy down"))
    def test_push_failure_is_logged_not_raised(self, _push):
        from .delivery import deliver_escalation
        with self.assertLogs("escalations", level="ERROR") as cm:
            deliver_escalation(make_escalation(tier=2))  # must not raise
        self.assertTrue(any("push FAILED" in m for m in cm.output))

    @override_settings(GUAF_TEST=True)
    @mock.patch("escalations.delivery.get_ntfy_topic_url", return_value="https://ntfy.sh/guaf-esc-ddf1fe5ab333")
    @mock.patch("escalations.delivery.requests.post")
    def test_push_never_targets_personal_topic(self, post, topic):
        from .delivery import send_escalation_push
        post.return_value = mock.Mock(raise_for_status=mock.Mock())
        send_escalation_push(make_escalation(tier=1))
        url = post.call_args.args[0]
        self.assertNotIn("aegis-brian-fischman", url)
        self.assertIn("guaf-esc-ddf1fe5ab333", url)


# ── Queue API: auth, ordering, filter, breach ───────────────────────────────
class QueueApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        Group.objects.get_or_create(name=ROLE_ADMIN)
        Group.objects.get_or_create(name=ROLE_CLIENT)
        self.admin = User.objects.create_superuser("boss", "boss@x.co", "pw")
        self.plain = User.objects.create_user("cli", "cli@x.co", "pw")
        self.plain.groups.add(Group.objects.get(name=ROLE_CLIENT))

    def test_list_requires_leadership(self):
        self.client.force_authenticate(self.plain)
        self.assertEqual(self.client.get(reverse("escalation-list")).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(reverse("escalation-list")).status_code, 401)

    def test_ordering_tier_then_deadline_then_confidence(self):
        now = timezone.now()
        # Tier 2, two deadlines/confidences; Tier 1 must sort first.
        make_escalation(tier=2, confidence=0.9, sla_deadline_at=now + timedelta(hours=10), trigger_id="legal_trouble")
        make_escalation(tier=1, confidence=0.5, sla_deadline_at=now + timedelta(hours=5), trigger_id="psychosis_signs")
        make_escalation(tier=2, confidence=0.4, sla_deadline_at=now + timedelta(hours=2), trigger_id="bankruptcy")
        # Same tier+deadline, confidence tiebreak DESC.
        make_escalation(tier=2, confidence=0.3, sla_deadline_at=now + timedelta(hours=2), trigger_id="bankruptcy")

        self.client.force_authenticate(self.admin)
        rows = self.client.get(reverse("escalation-list")).json()["results"]
        tiers = [r["tier"] for r in rows]
        self.assertEqual(tiers, [1, 2, 2, 2])
        # Within tier 2: deadline 2h (conf .4), deadline 2h (conf .3), deadline 10h.
        t2 = [r for r in rows if r["tier"] == 2]
        self.assertEqual([r["confidence"] for r in t2], [0.4, 0.3, 0.9])

    def test_status_filter_group(self):
        make_escalation(tier=1, status=STATUS_OPEN)
        make_escalation(tier=2, status=STATUS_IN_REVIEW)
        make_escalation(tier=3, status=STATUS_RESOLVED)
        self.client.force_authenticate(self.admin)
        opened = self.client.get(reverse("escalation-list"), {"status": "open"}).json()["results"]
        self.assertEqual(len(opened), 1)
        closed = self.client.get(reverse("escalation-list"), {"status": "closed"}).json()["results"]
        self.assertEqual(len(closed), 1)

    def test_breach_computed_not_stored(self):
        past = make_escalation(tier=1, sla_deadline_at=timezone.now() - timedelta(minutes=1))
        future = make_escalation(tier=2, sla_deadline_at=timezone.now() + timedelta(hours=1))
        self.client.force_authenticate(self.admin)
        detail_past = self.client.get(reverse("escalation-detail", args=[past.pk])).json()
        detail_future = self.client.get(reverse("escalation-detail", args=[future.pk])).json()
        self.assertTrue(detail_past["breached"])
        self.assertLess(detail_past["seconds_remaining"], 0)
        self.assertFalse(detail_future["breached"])
        self.assertGreater(detail_future["seconds_remaining"], 0)
        # Nothing named breach is persisted on the model.
        self.assertFalse(any(f.name == "breached" for f in Escalation._meta.get_fields()))

    def test_list_hides_full_name(self):
        make_escalation(tier=1, client_ref="Jane Doe")
        self.client.force_authenticate(self.admin)
        row = self.client.get(reverse("escalation-list")).json()["results"][0]
        self.assertNotIn("client_ref", row)
        self.assertNotIn("client_name", row)
        self.assertEqual(row["client_initials"], "JD")


# ── Lifecycle transitions + audit ───────────────────────────────────────────
class LifecycleTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        Group.objects.get_or_create(name=ROLE_ADMIN)
        self.admin = User.objects.create_superuser("boss", "boss@x.co", "pw")
        self.client.force_authenticate(self.admin)
        self.esc = make_escalation(tier=1, status=STATUS_OPEN)

    def _transition(self, to_status, note="", **extra):
        return self.client.post(
            reverse("escalation-transition", args=[self.esc.pk]),
            {"to_status": to_status, "note": note, **extra}, format="json",
        )

    def test_valid_path_writes_audit_rows(self):
        self.assertEqual(self._transition(STATUS_ACKNOWLEDGED).status_code, 200)
        self.assertEqual(self._transition(STATUS_IN_REVIEW).status_code, 200)
        resp = self._transition(
            STATUS_RESOLVED, note="Spoke with client",
            resolution_method="contacted-client",
        )
        self.assertEqual(resp.status_code, 200)
        self.esc.refresh_from_db()
        self.assertEqual(self.esc.status, STATUS_RESOLVED)
        moves = list(self.esc.transitions.values_list("from_status", "to_status"))
        self.assertIn((STATUS_OPEN, STATUS_ACKNOWLEDGED), moves)
        self.assertIn((STATUS_IN_REVIEW, STATUS_RESOLVED), moves)
        last = self.esc.transitions.order_by("-id").first()
        self.assertEqual(last.actor, self.admin)
        self.assertEqual(last.note, "Spoke with client")

    def test_invalid_transition_400_with_allowed_states(self):
        # open -> resolved is not allowed (must acknowledge -> in_review first).
        resp = self._transition(STATUS_RESOLVED)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["allowed_next_states"], [STATUS_ACKNOWLEDGED])
        self.esc.refresh_from_db()
        self.assertEqual(self.esc.status, STATUS_OPEN)

    def test_terminal_state_rejects_further_moves(self):
        self._transition(STATUS_ACKNOWLEDGED)
        self._transition(STATUS_IN_REVIEW)
        self._transition(STATUS_FALSE_POSITIVE, resolution_method="no-action-needed")
        resp = self._transition(STATUS_RESOLVED, resolution_method="contacted-client")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["allowed_next_states"], [])
        # false_positive record retained.
        self.esc.refresh_from_db()
        self.assertEqual(self.esc.status, STATUS_FALSE_POSITIVE)
        self.assertTrue(Escalation.objects.filter(pk=self.esc.pk).exists())

    def test_transition_requires_leadership(self):
        self.client.force_authenticate(None)
        self.assertEqual(self._transition(STATUS_ACKNOWLEDGED).status_code, 401)


# ── Resolution + archive ────────────────────────────────────────────────────
class ResolutionArchiveTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        Group.objects.get_or_create(name=ROLE_ADMIN)
        self.admin = User.objects.create_superuser("boss", "boss@x.co", "pw")
        self.client.force_authenticate(self.admin)

    def _in_review(self):
        esc = make_escalation(tier=1, status=STATUS_IN_REVIEW)
        return esc

    def _transition(self, esc, to_status, **body):
        return self.client.post(
            reverse("escalation-transition", args=[esc.pk]),
            {"to_status": to_status, **body}, format="json",
        )

    def test_seed_migration_ran(self):
        # The 0003 data migration seeded the full vocabulary.
        self.assertEqual(
            ResolutionMethod.objects.count(), len(DEFAULT_RESOLUTION_METHODS)
        )
        self.assertTrue(ResolutionMethod.objects.filter(slug="other").exists())

    def test_seed_idempotent(self):
        before = ResolutionMethod.objects.count()
        seed_resolution_methods(ResolutionMethod)
        seed_resolution_methods(ResolutionMethod)
        self.assertEqual(ResolutionMethod.objects.count(), before)

    def test_methods_endpoint_returns_active_only(self):
        ResolutionMethod.objects.filter(slug="other").update(active=False)
        body = self.client.get(reverse("escalation-methods")).json()
        rows = body["results"] if isinstance(body, dict) else body
        slugs = {r["slug"] for r in rows}
        self.assertIn("contacted-client", slugs)
        self.assertNotIn("other", slugs)

    def test_close_requires_method_each_closing_status(self):
        for closing in (STATUS_RESOLVED, STATUS_FALSE_POSITIVE, STATUS_ESCALATED_TO_CLINICAL):
            esc = self._in_review()
            resp = self._transition(esc, closing)  # no resolution_method
            self.assertEqual(resp.status_code, 400, closing)
            # 400 body lists the methods for the UI.
            names = {m["slug"] for m in resp.json()["resolution_methods"]}
            self.assertIn("contacted-client", names)
            esc.refresh_from_db()
            self.assertEqual(esc.status, STATUS_IN_REVIEW)  # unchanged
            self.assertIsNone(esc.archived_at)

    def test_inactive_method_rejected(self):
        ResolutionMethod.objects.filter(slug="contacted-client").update(active=False)
        esc = self._in_review()
        resp = self._transition(esc, STATUS_RESOLVED, resolution_method="contacted-client")
        self.assertEqual(resp.status_code, 400)

    def test_other_requires_note(self):
        esc = self._in_review()
        resp = self._transition(esc, STATUS_RESOLVED, resolution_method="other")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("note", resp.json()["detail"].lower())
        esc.refresh_from_db()
        self.assertEqual(esc.status, STATUS_IN_REVIEW)
        # With a note it closes.
        resp = self._transition(
            esc, STATUS_RESOLVED, resolution_method="other", resolution_note="Bespoke plan."
        )
        self.assertEqual(resp.status_code, 200)

    def test_close_stamps_resolution_and_archive_and_audit(self):
        esc = self._in_review()
        resp = self._transition(
            esc, STATUS_RESOLVED,
            resolution_method="contacted-client", resolution_note="Reached out.",
        )
        self.assertEqual(resp.status_code, 200)
        esc.refresh_from_db()
        self.assertEqual(esc.status, STATUS_RESOLVED)
        self.assertEqual(esc.resolution_method.slug, "contacted-client")
        self.assertEqual(esc.resolution_note, "Reached out.")
        self.assertEqual(esc.resolved_by, self.admin)
        self.assertIsNotNone(esc.resolved_at)
        self.assertIsNotNone(esc.archived_at)
        # Audit row carries method + note.
        row = esc.transitions.order_by("-id").first()
        self.assertEqual(row.to_status, STATUS_RESOLVED)
        self.assertEqual(row.resolution_method.slug, "contacted-client")
        self.assertEqual(row.resolution_note, "Reached out.")
        # Detail serializer surfaces it.
        detail = self.client.get(reverse("escalation-detail", args=[esc.pk])).json()
        last = detail["transitions"][-1]
        self.assertEqual(last["resolution_method_slug"], "contacted-client")
        self.assertEqual(detail["resolution_method_name"], "Contacted client")

    def test_archive_filtering(self):
        # One live (open) + one closed → archived.
        make_escalation(tier=2, status=STATUS_OPEN)
        closed = self._in_review()
        self._transition(closed, STATUS_RESOLVED, resolution_method="no-action-needed")

        default = self.client.get(reverse("escalation-list")).json()["results"]
        ids = {r["id"] for r in default}
        self.assertNotIn(closed.id, ids)  # archived excluded by default

        archived = self.client.get(
            reverse("escalation-list"), {"archived": "true"}
        ).json()["results"]
        aids = {r["id"] for r in archived}
        self.assertEqual(aids, {closed.id})
        # Archive row carries who/when/method for the card.
        card = archived[0]
        self.assertEqual(card["resolution_method_slug"], "no-action-needed")
        self.assertIsNotNone(card["archived_at"])
        self.assertIsNotNone(card["resolved_by_name"])

    def test_reopen_path_and_audit(self):
        esc = self._in_review()
        self._transition(esc, STATUS_RESOLVED, resolution_method="contacted-client")
        esc.refresh_from_db()
        self.assertIsNotNone(esc.archived_at)

        resp = self.client.post(reverse("escalation-reopen", args=[esc.pk]), {}, format="json")
        self.assertEqual(resp.status_code, 200)
        esc.refresh_from_db()
        self.assertEqual(esc.status, STATUS_IN_REVIEW)
        self.assertIsNone(esc.archived_at)
        self.assertIsNone(esc.resolution_method)
        self.assertIsNone(esc.resolved_by)
        self.assertIsNone(esc.resolved_at)
        # Reopen is audited.
        row = esc.transitions.order_by("-id").first()
        self.assertEqual(row.to_status, STATUS_IN_REVIEW)
        self.assertEqual(row.actor, self.admin)
        # And the close row (with its resolution) is retained in the trail.
        self.assertTrue(
            esc.transitions.filter(to_status=STATUS_RESOLVED, resolution_method__isnull=False).exists()
        )

    def test_reopen_rejects_non_archived(self):
        esc = self._in_review()
        resp = self.client.post(reverse("escalation-reopen", args=[esc.pk]), {}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_reopen_requires_leadership(self):
        esc = self._in_review()
        self._transition(esc, STATUS_RESOLVED, resolution_method="contacted-client")
        self.client.force_authenticate(None)
        resp = self.client.post(reverse("escalation-reopen", args=[esc.pk]), {}, format="json")
        self.assertEqual(resp.status_code, 401)


# ── Loader / triggers.yaml ──────────────────────────────────────────────────
class TriggerSpecTests(TestCase):
    def test_yaml_loads_and_tier1_is_calendar(self):
        from .loader import load_triggers
        spec = load_triggers()
        self.assertEqual(spec.sla_for_tier(1).clock, "calendar")
        self.assertEqual(spec.sla_for_tier(1).hours, 12)
        self.assertEqual(spec.sla_for_tier(2).clock, "business_hours")
        self.assertEqual(spec.sla_for_tier(2).hours, 24)
        self.assertEqual(spec.sla_for_tier(3).hours, 72)
        self.assertEqual(spec.by_id["suicidal_thought"].tier, 1)
