import os
import tempfile
from io import BytesIO
from unittest import mock

from django.contrib.auth.models import Group, User
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from .constants import ROLE_CLIENT, ROLE_COACH
from .models import ClientOnboarding, UserProfile
from .storage import R2MediaStorage, is_configured

R2_ENV = {
    "R2_ACCOUNT_ID": "test-account",
    "R2_ACCESS_KEY_ID": "test-key",
    "R2_SECRET_ACCESS_KEY": "test-secret",
    "R2_BUCKET": "test-bucket",
}


def make_photo_upload(name="photo.png"):
    buffer = BytesIO()
    Image.new("RGB", (2, 2), color=(220, 90, 60)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class AuthenticationFlowTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.coach_group = Group.objects.get(name=ROLE_COACH)
        cls.client_group = Group.objects.get(name=ROLE_CLIENT)

        cls.coach = User.objects.create_user(
            username="coach1",
            password="Pass12345!",
            email="coach@example.com",
            first_name="Casey",
        )
        cls.coach.groups.add(cls.coach_group)

        cls.client_user = User.objects.create_user(
            username="client1",
            password="Pass12345!",
            email="client@example.com",
            first_name="Jordan",
        )
        cls.client_user.groups.add(cls.client_group)
        cls.client_user.profile.assigned_coach = cls.coach
        cls.client_user.profile.save()

    def test_valid_login_issues_tokens_and_user_payload(self):
        response = self.client.post(
            reverse("login"),
            {"username": "client1", "password": "Pass12345!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["role"], ROLE_CLIENT)

    def test_invalid_login_is_rejected(self):
        response = self.client.post(
            reverse("login"),
            {"username": "client1", "password": "wrong-password"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_endpoint_identifies_user_role_and_assigned_coach(self):
        login_response = self.client.post(
            reverse("login"),
            {"username": "client1", "password": "Pass12345!"},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_response.data['access']}")

        response = self.client.get(reverse("me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], ROLE_CLIENT)
        self.assertEqual(response.data["profile"]["assigned_coach_name"], "Casey")


class CoachCardTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        coach_group = Group.objects.get(name=ROLE_COACH)
        client_group = Group.objects.get(name=ROLE_CLIENT)

        cls.coach_one = User.objects.create_user(username="coach1", password="Pass12345!", first_name="Casey")
        cls.coach_one.groups.add(coach_group)
        cls.coach_one.profile.bio = "Movement and recovery specialist."
        cls.coach_one.profile.contact_email = "casey@coaching.example.com"
        cls.coach_one.profile.contact_phone = "+1 555 0101"
        cls.coach_one.profile.save()

        cls.coach_two = User.objects.create_user(username="coach2", password="Pass12345!", first_name="Morgan")
        cls.coach_two.groups.add(coach_group)
        cls.coach_two.profile.bio = "Strength coach."
        cls.coach_two.profile.save()

        cls.client_one = User.objects.create_user(username="client1", password="Pass12345!")
        cls.client_one.groups.add(client_group)
        cls.client_one.profile.assigned_coach = cls.coach_one
        cls.client_one.profile.save()

        cls.client_two = User.objects.create_user(username="client2", password="Pass12345!")
        cls.client_two.groups.add(client_group)
        cls.client_two.profile.assigned_coach = cls.coach_two
        cls.client_two.profile.save()

    def authenticate(self, user):
        response = self.client.post(
            reverse("login"),
            {"username": user.username, "password": "Pass12345!"},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_client_me_includes_own_coach_card(self):
        self.authenticate(self.client_one)

        response = self.client.get(reverse("me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        card = response.data["my_coach"]
        self.assertEqual(card["id"], self.coach_one.id)
        self.assertEqual(card["name"], "Casey")
        self.assertEqual(card["bio"], "Movement and recovery specialist.")
        self.assertEqual(card["contact_email"], "casey@coaching.example.com")
        self.assertEqual(card["contact_phone"], "+1 555 0101")
        self.assertIsNone(card["photo_url"])

    def test_client_only_sees_own_coach_card_in_assignments(self):
        self.authenticate(self.client_one)

        response = self.client.get(reverse("client-assignment-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = response.data["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["user"]["id"], self.client_one.id)
        self.assertEqual(rows[0]["coach"]["id"], self.coach_one.id)
        self.assertEqual(rows[0]["coach"]["bio"], "Movement and recovery specialist.")

    def test_coach_assignments_never_expose_other_coaches_cards(self):
        self.authenticate(self.coach_one)

        response = self.client.get(reverse("client-assignment-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = response.data["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual({row["coach"]["id"] for row in rows}, {self.coach_one.id})

    def test_coach_me_has_no_coach_card(self):
        self.authenticate(self.coach_one)

        response = self.client.get(reverse("me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["my_coach"])


class AccountSettingsUpdateTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        coach_group = Group.objects.get(name=ROLE_COACH)
        cls.coach = User.objects.create_user(username="coach1", password="Pass12345!", first_name="Casey")
        cls.coach.groups.add(coach_group)

    def authenticate(self, user):
        response = self.client.post(
            reverse("login"),
            {"username": user.username, "password": "Pass12345!"},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_profile_fields_round_trip(self):
        self.authenticate(self.coach)

        response = self.client.patch(
            reverse("me"),
            {
                "bio": "Here to keep you moving.",
                "contact_email": "casey@coaching.example.com",
                "contact_phone": "+1 555 0101",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["profile"]["bio"], "Here to keep you moving.")
        self.assertEqual(response.data["profile"]["contact_email"], "casey@coaching.example.com")
        self.assertEqual(response.data["profile"]["contact_phone"], "+1 555 0101")

        profile = UserProfile.objects.get(user=self.coach)
        self.assertEqual(profile.bio, "Here to keep you moving.")
        self.assertEqual(profile.contact_email, "casey@coaching.example.com")
        self.assertEqual(profile.contact_phone, "+1 555 0101")

        follow_up = self.client.get(reverse("me"))
        self.assertEqual(follow_up.data["profile"]["bio"], "Here to keep you moving.")

    @mock.patch.dict(os.environ, {name: "" for name in R2_ENV})
    def test_photo_upload_without_storage_env_returns_clear_400(self):
        self.authenticate(self.coach)

        response = self.client.patch(reverse("me"), {"photo": make_photo_upload()}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Photo storage is not configured yet.", response.data["photo"])
        self.assertFalse(UserProfile.objects.get(user=self.coach).photo)

    @mock.patch("accounts.storage.is_configured", return_value=True)
    def test_photo_upload_round_trips_when_storage_configured(self, _is_configured):
        # The model field's storage was resolved without R2 env, so uploads land
        # in MEDIA_ROOT — R2/boto3 stays fully mocked out and offline.
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                self.authenticate(self.coach)

                response = self.client.patch(reverse("me"), {"photo": make_photo_upload()}, format="multipart")

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertTrue(response.data["profile"]["photo_url"].startswith("http"))
                self.assertIn("coach-photos/", response.data["profile"]["photo_url"])

                profile = UserProfile.objects.get(user=self.coach)
                self.assertTrue(profile.photo.name.startswith("coach-photos/"))


class PasswordResetFlowTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="client@example.com",
            email="client@example.com",
            password="OldPass123!",
            first_name="Jordan",
        )
        cls.user.groups.add(Group.objects.get(name=ROLE_CLIENT))

    def setUp(self):
        cache.clear()  # scoped throttle state must not leak between tests

    def tearDown(self):
        cache.clear()

    def request_reset(self, email):
        return self.client.post(reverse("password-reset"), {"email": email}, format="json")

    def extract_reset_params(self, body):
        # The email link looks like {APP_BASE_URL}/reset-password?uid=..&token=..
        url = next(line for line in body.splitlines() if "/reset-password?" in line).strip()
        query = url.split("?", 1)[1]
        return dict(pair.split("=", 1) for pair in query.split("&"))

    def test_reset_request_sends_email_with_working_link(self):
        response = self.request_reset("client@example.com")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["client@example.com"])
        self.assertIn("Reset your Get Up and Flow password", message.subject)

        params = self.extract_reset_params(message.body)
        confirm = self.client.post(
            reverse("password-reset-confirm"),
            {"uid": params["uid"], "token": params["token"], "new_password": "NewPass456!"},
            format="json",
        )
        self.assertEqual(confirm.status_code, status.HTTP_200_OK)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPass456!"))

        login = self.client.post(
            reverse("login"),
            {"username": "client@example.com", "password": "NewPass456!"},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)

    def test_unknown_email_returns_200_without_sending(self):
        response = self.request_reset("nobody@example.com")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_inactive_user_gets_no_reset_email(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.request_reset("client@example.com")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_confirm_rejects_bad_token(self):
        self.request_reset("client@example.com")
        params = self.extract_reset_params(mail.outbox[0].body)
        response = self.client.post(
            reverse("password-reset-confirm"),
            {"uid": params["uid"], "token": "bad-token", "new_password": "NewPass456!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("OldPass123!"))

    def test_token_is_single_use(self):
        self.request_reset("client@example.com")
        params = self.extract_reset_params(mail.outbox[0].body)
        payload = {"uid": params["uid"], "token": params["token"], "new_password": "NewPass456!"}
        first = self.client.post(reverse("password-reset-confirm"), payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        payload["new_password"] = "OtherPass789!"
        second = self.client.post(reverse("password-reset-confirm"), payload, format="json")
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)

    def test_confirm_runs_password_validators(self):
        self.request_reset("client@example.com")
        params = self.extract_reset_params(mail.outbox[0].body)
        response = self.client.post(
            reverse("password-reset-confirm"),
            {"uid": params["uid"], "token": params["token"], "new_password": "12345678"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("new_password", response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("OldPass123!"))

    def test_confirm_rejects_garbage_uid(self):
        response = self.client.post(
            reverse("password-reset-confirm"),
            {"uid": "!!not-base64!!", "token": "whatever", "new_password": "NewPass456!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class OnboardingTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.coach = User.objects.create_user(username="coach1", password="Pass12345!")
        cls.coach.groups.add(Group.objects.get(name=ROLE_COACH))
        cls.client_user = User.objects.create_user(
            username="client1", password="Pass12345!", email="client@example.com"
        )
        cls.client_user.groups.add(Group.objects.get(name=ROLE_CLIENT))

    def authenticate(self, user):
        response = self.client.post(
            reverse("login"),
            {"username": user.username, "password": "Pass12345!"},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def onboarding_payload(self, **overrides):
        payload = {
            "timezone": "America/New_York",
            "morning_window": "8-10am",
            "evening_window": "6-8pm",
            "contact_method": "whatsapp",
            "contact_number": "+1 555 0199",
            "help_topics": "Getting mornings started without spiraling.",
        }
        payload.update(overrides)
        return payload

    def test_requires_authentication(self):
        self.assertEqual(
            self.client.get(reverse("onboarding")).status_code, status.HTTP_401_UNAUTHORIZED
        )

    def test_coach_cannot_access_onboarding(self):
        self.authenticate(self.coach)
        self.assertEqual(
            self.client.get(reverse("onboarding")).status_code, status.HTTP_403_FORBIDDEN
        )

    def test_get_returns_null_before_first_save(self):
        self.authenticate(self.client_user)
        response = self.client.get(reverse("onboarding"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data)

    def test_put_creates_and_updates_answers(self):
        self.authenticate(self.client_user)
        response = self.client.put(reverse("onboarding"), self.onboarding_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data["completed_at"])

        onboarding = ClientOnboarding.objects.get(user=self.client_user)
        self.assertEqual(onboarding.timezone, "America/New_York")
        self.assertEqual(onboarding.contact_method, "whatsapp")
        first_completed_at = onboarding.completed_at

        update = self.client.put(
            reverse("onboarding"),
            self.onboarding_payload(morning_window="6-8am", contact_method="sms"),
            format="json",
        )
        self.assertEqual(update.status_code, status.HTTP_200_OK)
        onboarding.refresh_from_db()
        self.assertEqual(onboarding.morning_window, "6-8am")
        self.assertEqual(onboarding.contact_method, "sms")
        self.assertEqual(onboarding.completed_at, first_completed_at)
        self.assertEqual(ClientOnboarding.objects.filter(user=self.client_user).count(), 1)

    def test_rejects_invalid_timezone_window_and_contact_method(self):
        self.authenticate(self.client_user)
        for overrides in (
            {"timezone": "Mars/Olympus_Mons"},
            {"morning_window": "midnight"},
            {"evening_window": "midnight"},
            {"contact_method": "carrier_pigeon"},
            {"contact_number": ""},
        ):
            response = self.client.put(
                reverse("onboarding"), self.onboarding_payload(**overrides), format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, overrides)

    def test_me_reports_onboarding_completeness(self):
        self.authenticate(self.client_user)
        self.assertFalse(self.client.get(reverse("me")).data["onboarding_complete"])
        self.client.put(reverse("onboarding"), self.onboarding_payload(), format="json")
        self.assertTrue(self.client.get(reverse("me")).data["onboarding_complete"])


class CoachAssignmentQueueTests(APITestCase):
    """The Django admin queue lists exactly the active paid clients with no coach."""

    @classmethod
    def setUpTestData(cls):
        from billing.models import Subscription

        cls.Subscription = Subscription
        cls.coach = User.objects.create_user(username="coach1", password="Pass12345!")
        cls.coach.groups.add(Group.objects.get(name=ROLE_COACH))

        def make_client(username, active=True, coach=None, sub_status=None):
            user = User.objects.create_user(
                username=username, email=f"{username}@example.com", password="Pass12345!",
                is_active=active,
            )
            user.groups.add(Group.objects.get(name=ROLE_CLIENT))
            if coach:
                user.profile.assigned_coach = coach
                user.profile.save()
            if sub_status:
                Subscription.objects.create(
                    user=user, stripe_subscription_id=f"sub_{username}", status=sub_status
                )
            return user

        cls.waiting = make_client("waiting", sub_status="active")
        cls.past_due = make_client("pastdue", sub_status="past_due")
        cls.assigned = make_client("assigned", coach=cls.coach, sub_status="active")
        cls.unpaid = make_client("unpaid")
        cls.inactive = make_client("inactive", active=False, sub_status="active")
        cls.canceled = make_client("canceled", sub_status="canceled")

    def get_queue_queryset(self):
        from django.contrib.admin.sites import site

        from .admin import CoachAssignmentQueueEntry

        model_admin = site._registry[CoachAssignmentQueueEntry]
        request = mock.Mock()
        return model_admin.get_queryset(request), model_admin

    def test_queue_contains_only_active_paid_unassigned_clients(self):
        queryset, _ = self.get_queue_queryset()
        self.assertEqual(
            {entry.user.username for entry in queryset}, {"waiting", "pastdue"}
        )

    def test_hours_since_payment_highlights_older_than_24h(self):
        from datetime import timedelta

        from django.utils import timezone

        queryset, model_admin = self.get_queue_queryset()
        entry = queryset.get(user=self.waiting)

        fresh = model_admin.hours_since_payment(entry)
        self.assertNotIn("<strong", str(fresh))

        self.Subscription.objects.filter(user=self.waiting).update(
            created_at=timezone.now() - timedelta(hours=30)
        )
        entry = self.get_queue_queryset()[0].get(user=self.waiting)
        stale = model_admin.hours_since_payment(entry)
        self.assertIn("<strong", str(stale))
        self.assertIn("30h", str(stale))


class R2StorageTests(SimpleTestCase):
    @mock.patch.dict(os.environ, {name: "" for name in R2_ENV})
    def test_not_configured_without_env(self):
        self.assertFalse(is_configured())

    @mock.patch.dict(os.environ, R2_ENV)
    def test_storage_points_at_r2_endpoint(self):
        self.assertTrue(is_configured())

        storage = R2MediaStorage()

        self.assertEqual(storage.endpoint_url, "https://test-account.r2.cloudflarestorage.com")
        self.assertEqual(storage.bucket_name, "test-bucket")
        self.assertEqual(storage.access_key, "test-key")
        self.assertEqual(storage.secret_key, "test-secret")
        self.assertFalse(storage.file_overwrite)

    @mock.patch.dict(os.environ, {**R2_ENV, "R2_PUBLIC_BASE_URL": "https://pub-abc123.r2.dev/"})
    def test_public_base_url_serves_unsigned_urls(self):
        storage = R2MediaStorage()

        self.assertEqual(storage.custom_domain, "pub-abc123.r2.dev")
        self.assertFalse(storage.querystring_auth)
        self.assertEqual(storage.url("coach-photos/casey.png"), "https://pub-abc123.r2.dev/coach-photos/casey.png")
