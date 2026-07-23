from unittest import mock

from django.contrib.auth.models import Group, User
from django.core import mail
from django.test import TestCase, override_settings

from accounts.constants import ROLE_CLIENT, ROLE_COACH
from billing.models import Subscription

from .emails import send_coach_assigned_email, send_templated_email, send_welcome_email
from .ntfy import send_ntfy
from .provider import (
    CONSOLE_BACKEND,
    POSTMARK_BACKEND,
    RESEND_BACKEND,
    select_email_backend,
)


class ProviderSelectionTests(TestCase):
    def test_postmark_selected_with_token(self):
        backend, anymail = select_email_backend("postmark", postmark_server_token="pm-token")
        self.assertEqual(backend, POSTMARK_BACKEND)
        self.assertEqual(anymail, {"POSTMARK_SERVER_TOKEN": "pm-token"})

    def test_resend_selected_with_key(self):
        backend, anymail = select_email_backend("resend", resend_api_key="re-key")
        self.assertEqual(backend, RESEND_BACKEND)
        self.assertEqual(anymail, {"RESEND_API_KEY": "re-key"})

    def test_provider_without_credentials_falls_back_to_console(self):
        self.assertEqual(select_email_backend("postmark")[0], CONSOLE_BACKEND)
        self.assertEqual(select_email_backend("resend")[0], CONSOLE_BACKEND)

    def test_unset_or_unknown_provider_falls_back_to_console(self):
        self.assertEqual(select_email_backend(None)[0], CONSOLE_BACKEND)
        self.assertEqual(select_email_backend("")[0], CONSOLE_BACKEND)
        self.assertEqual(select_email_backend("console")[0], CONSOLE_BACKEND)
        self.assertEqual(select_email_backend("sendgrid", "tok", "key")[0], CONSOLE_BACKEND)

    def test_provider_name_is_normalized(self):
        backend, _ = select_email_backend("  Postmark ", postmark_server_token="pm-token")
        self.assertEqual(backend, POSTMARK_BACKEND)


class TemplatedEmailTests(TestCase):
    def test_sends_plain_and_html_alternative(self):
        sent = send_templated_email(
            "client@example.com", "Welcome to Get Up and Flow — you're in", "welcome",
            {"first_name": "Ada", "plan_name": "Full Support"},
        )
        self.assertTrue(sent)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["client@example.com"])
        self.assertIn("Ada", message.body)
        self.assertNotIn("<html", message.body)
        html_bodies = [body for body, mimetype in message.alternatives if mimetype == "text/html"]
        self.assertEqual(len(html_bodies), 1)
        self.assertIn("Ada", html_bodies[0])

    def test_send_failure_is_swallowed_and_logged(self):
        with mock.patch("notifications.emails.EmailMultiAlternatives") as mock_email:
            mock_email.side_effect = RuntimeError("provider down")
            with self.assertLogs("notifications", level="ERROR"):
                sent = send_templated_email("client@example.com", "Subject", "welcome", {})
        self.assertFalse(sent)

    def test_welcome_email_sets_expectations(self):
        user = User.objects.create_user(
            username="w@example.com", email="w@example.com", first_name="Wes"
        )
        send_welcome_email(user, "Focus Lite")
        body = mail.outbox[0].body
        self.assertIn("within 48 hours", body)
        self.assertIn("usually within 12", body)
        self.assertIn("Focus Lite", body)
        self.assertIn("/app/onboarding", body)
        self.assertIn("hello@getupandflow.co", body)

    def test_coach_assigned_email_names_the_coach(self):
        client = User.objects.create_user(
            username="c@example.com", email="c@example.com", first_name="Cleo"
        )
        coach = User.objects.create_user(
            username="coach@example.com", email="coach@example.com", first_name="Morgan"
        )
        send_coach_assigned_email(client, coach)
        message = mail.outbox[0]
        self.assertIn("Morgan", message.subject)
        self.assertIn("Morgan", message.body)
        self.assertIn("first check-in", message.body)
        self.assertIn("/login", message.body)


class NtfyTests(TestCase):
    @mock.patch("notifications.ntfy.requests")
    def test_post_failure_is_swallowed(self, mock_requests):
        mock_requests.post.side_effect = RuntimeError("network down")
        with self.assertLogs("notifications", level="ERROR"):
            self.assertFalse(send_ntfy("hello"))

    @override_settings(NTFY_TOPIC_URL="")
    @mock.patch("notifications.ntfy.requests")
    def test_empty_topic_disables_ntfy(self, mock_requests):
        self.assertFalse(send_ntfy("hello"))
        mock_requests.post.assert_not_called()


@override_settings(NTFY_TOPIC_URL="")
class CoachAssignmentEmailTests(TestCase):
    def setUp(self):
        self.coach = User.objects.create_user(
            username="coach", email="coach@example.com", first_name="Morgan"
        )
        self.coach.groups.add(Group.objects.get(name=ROLE_COACH))
        self.client_user = User.objects.create_user(
            username="paid@example.com", email="paid@example.com", first_name="Cleo"
        )
        self.client_user.groups.add(Group.objects.get(name=ROLE_CLIENT))

    def make_paid(self, user, sub_id="sub_abc"):
        return Subscription.objects.create(
            user=user, stripe_subscription_id=sub_id, status=Subscription.STATUS_ACTIVE
        )

    def assign_coach(self, user):
        profile = user.profile
        profile.assigned_coach = self.coach
        profile.save()

    def test_assigning_coach_to_paid_client_sends_email(self):
        self.make_paid(self.client_user)
        self.assign_coach(self.client_user)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["paid@example.com"])
        self.assertIn("Morgan", message.subject)

    def test_assignment_via_admin_queue_proxy_sends_email(self):
        # Proxy saves dispatch signals with the proxy as sender; the receivers
        # must still fire (regression: sender=UserProfile registration missed them).
        from accounts.admin import CoachAssignmentQueueEntry

        self.make_paid(self.client_user)
        entry = CoachAssignmentQueueEntry.objects.get(user=self.client_user)
        entry.assigned_coach = self.coach
        entry.save()
        self.assertEqual(len(mail.outbox), 1)

    def test_reassignment_does_not_resend_email(self):
        self.make_paid(self.client_user)
        self.assign_coach(self.client_user)
        other_coach = User.objects.create_user(
            username="coach2", email="coach2@example.com", first_name="Riley"
        )
        other_coach.groups.add(Group.objects.get(name=ROLE_COACH))
        profile = self.client_user.profile
        profile.assigned_coach = other_coach
        profile.save()
        self.assertEqual(len(mail.outbox), 1)

    def test_unpaid_manual_client_gets_no_email(self):
        self.assign_coach(self.client_user)
        self.assertEqual(len(mail.outbox), 0)

    def test_past_due_client_still_gets_email(self):
        subscription = self.make_paid(self.client_user)
        subscription.status = Subscription.STATUS_PAST_DUE
        subscription.save()
        self.assign_coach(self.client_user)
        self.assertEqual(len(mail.outbox), 1)

    def test_canceled_client_gets_no_email(self):
        subscription = self.make_paid(self.client_user)
        subscription.status = Subscription.STATUS_CANCELED
        subscription.save()
        self.assign_coach(self.client_user)
        self.assertEqual(len(mail.outbox), 0)

    def test_inactive_client_gets_no_email(self):
        self.make_paid(self.client_user)
        self.client_user.is_active = False
        self.client_user.save(update_fields=["is_active"])
        self.assign_coach(self.client_user)
        self.assertEqual(len(mail.outbox), 0)
