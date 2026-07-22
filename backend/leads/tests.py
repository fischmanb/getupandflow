from unittest.mock import patch

from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.throttling import ScopedRateThrottle

from .models import Lead


class LeadCreateTests(APITestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def submit(self, **overrides):
        payload = {
            "full_name": "Jordan Example",
            "email": "jordan@example.com",
            "plan": Lead.PLAN_FULL_SUPPORT,
            "billing_period": Lead.BILLING_MONTHLY,
            "notes": "Help with morning planning.",
        }
        payload.update(overrides)
        return self.client.post(reverse("lead-create"), payload, format="json")

    def test_anonymous_post_creates_lead(self):
        response = self.submit()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        lead = Lead.objects.get()
        self.assertEqual(lead.full_name, "Jordan Example")
        self.assertEqual(lead.email, "jordan@example.com")
        self.assertEqual(lead.plan, Lead.PLAN_FULL_SUPPORT)
        self.assertEqual(lead.billing_period, Lead.BILLING_MONTHLY)
        self.assertEqual(lead.notes, "Help with morning planning.")
        self.assertIsNotNone(lead.created_at)

    def test_notes_are_optional(self):
        response = self.submit(notes="")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Lead.objects.get().notes, "")

    def test_invalid_email_is_rejected(self):
        response = self.submit(email="not-an-email")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)
        self.assertEqual(Lead.objects.count(), 0)

    def test_missing_full_name_is_rejected(self):
        response = self.client.post(
            reverse("lead-create"),
            {"email": "jordan@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("full_name", response.data)

    def test_unknown_plan_is_rejected(self):
        response = self.submit(plan="platinum")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("plan", response.data)

    def test_get_is_not_allowed(self):
        response = self.client.get(reverse("lead-create"))

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    @patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"leads": "3/hour"})
    def test_submissions_are_throttled(self):
        for index in range(3):
            response = self.submit(email=f"jordan{index}@example.com")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.submit(email="jordan-final@example.com")
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


class LeadCorsTests(APITestCase):
    def test_marketing_origin_is_allowed(self):
        response = self.client.options(
            reverse("lead-create"),
            HTTP_ORIGIN="https://getupandflow.co",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )

        self.assertEqual(
            response.headers.get("Access-Control-Allow-Origin"),
            "https://getupandflow.co",
        )

    def test_www_marketing_origin_is_allowed(self):
        response = self.client.options(
            reverse("lead-create"),
            HTTP_ORIGIN="https://www.getupandflow.co",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )

        self.assertEqual(
            response.headers.get("Access-Control-Allow-Origin"),
            "https://www.getupandflow.co",
        )
