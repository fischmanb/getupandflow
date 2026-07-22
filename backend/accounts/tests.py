import os
import tempfile
from io import BytesIO
from unittest import mock

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from .constants import ROLE_CLIENT, ROLE_COACH
from .models import UserProfile
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
