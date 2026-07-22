import os
from datetime import date, datetime, time
from unittest import mock

import requests
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.constants import ROLE_ADMIN, ROLE_CLIENT, ROLE_COACH
from accounts.models import UserProfile

from . import zoom
from .models import Event, EventCategory, Task
from .recurrence import expand_event_dates


def get_list_results(response):
    data = response.data
    return data["results"] if isinstance(data, dict) and "results" in data else data


class PlannerRBACAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_group = Group.objects.get(name=ROLE_ADMIN)
        cls.coach_group = Group.objects.get(name=ROLE_COACH)
        cls.client_group = Group.objects.get(name=ROLE_CLIENT)

        cls.admin = User.objects.create_user(username="admin1", password="Pass12345!", first_name="Alex")
        cls.admin.groups.add(cls.admin_group)

        cls.coach_one = User.objects.create_user(username="coach1", password="Pass12345!", first_name="Casey")
        cls.coach_one.groups.add(cls.coach_group)

        cls.coach_two = User.objects.create_user(username="coach2", password="Pass12345!", first_name="Morgan")
        cls.coach_two.groups.add(cls.coach_group)

        cls.client_one = User.objects.create_user(username="client1", password="Pass12345!", first_name="Jordan")
        cls.client_one.groups.add(cls.client_group)
        cls.client_one.profile.assigned_coach = cls.coach_one
        cls.client_one.profile.save()

        cls.client_two = User.objects.create_user(username="client2", password="Pass12345!", first_name="Taylor")
        cls.client_two.groups.add(cls.client_group)
        cls.client_two.profile.assigned_coach = cls.coach_two
        cls.client_two.profile.save()

        cls.category = EventCategory.objects.create(name="Wellness", color="emerald", client=cls.client_one)
        cls.category_two = EventCategory.objects.create(name="Recovery", color="sky", client=cls.client_two)

        cls.client_one_event = Event.objects.create(
            title="Mobility Session",
            event_date=date(2026, 3, 20),
            start_time=time(9, 0),
            end_time=time(10, 0),
            location="Studio A",
            description="Morning mobility work",
            category=cls.category,
            client=cls.client_one,
        )
        cls.client_two_event = Event.objects.create(
            title="Strength Session",
            event_date=date(2026, 3, 21),
            start_time=time(11, 0),
            end_time=time(12, 0),
            location="Studio B",
            description="Strength block",
            category=cls.category_two,
            client=cls.client_two,
        )
        cls.client_one_task = Task.objects.create(
            title="Hydration Check-in",
            deadline=timezone.make_aware(datetime(2026, 3, 22, 12, 0)),
            description="Log water intake",
            client=cls.client_one,
            completed_at=timezone.make_aware(datetime(2026, 3, 22, 10, 0)),
        )
        cls.client_two_task = Task.objects.create(
            title="Meal Prep",
            deadline=timezone.make_aware(datetime(2026, 3, 23, 15, 0)),
            description="Prepare meals for the week",
            client=cls.client_two,
        )

    def authenticate(self, user):
        response = self.client.post(
            reverse("login"),
            {"username": user.username, "password": "Pass12345!"},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_client_can_only_fetch_their_own_data(self):
        self.authenticate(self.client_one)

        events_response = self.client.get(reverse("event-list"))
        tasks_response = self.client.get(reverse("task-list"))
        forbidden_event_response = self.client.get(reverse("event-detail", args=[self.client_two_event.id]))

        self.assertEqual(events_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(get_list_results(events_response)), 1)
        self.assertEqual(get_list_results(events_response)[0]["id"], self.client_one_event.id)
        self.assertEqual(tasks_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(get_list_results(tasks_response)), 1)
        self.assertEqual(get_list_results(tasks_response)[0]["id"], self.client_one_task.id)
        self.assertEqual(forbidden_event_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_coach_cannot_fetch_unassigned_client_data(self):
        self.authenticate(self.coach_one)

        events_response = self.client.get(reverse("event-list"))
        tasks_response = self.client.get(reverse("task-list"))
        forbidden_task_response = self.client.get(reverse("task-detail", args=[self.client_two_task.id]))

        self.assertEqual(events_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(get_list_results(events_response)), 1)
        self.assertEqual(get_list_results(events_response)[0]["id"], self.client_one_event.id)
        self.assertEqual(tasks_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(get_list_results(tasks_response)), 1)
        self.assertEqual(get_list_results(tasks_response)[0]["id"], self.client_one_task.id)
        self.assertEqual(forbidden_task_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_can_fetch_all_events_and_tasks(self):
        self.authenticate(self.admin)

        events_response = self.client.get(reverse("event-list"))
        tasks_response = self.client.get(reverse("task-list"))

        self.assertEqual(events_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(get_list_results(events_response)), 2)
        self.assertEqual(tasks_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(get_list_results(tasks_response)), 2)

    def test_admin_can_filter_events_by_selected_clients(self):
        self.authenticate(self.admin)

        response = self.client.get(reverse("event-list"), {"client_ids": str(self.client_one.id)})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(get_list_results(response)), 1)
        self.assertEqual(get_list_results(response)[0]["id"], self.client_one_event.id)

    def test_admin_can_filter_tasks_by_selected_clients(self):
        self.authenticate(self.admin)

        response = self.client.get(reverse("task-list"), {"client_ids": str(self.client_one.id)})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = get_list_results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.client_one_task.id)

    def test_task_filter_with_empty_or_invalid_client_ids_returns_empty(self):
        self.authenticate(self.admin)

        response = self.client.get(reverse("task-list"), {"client_ids": "not-a-number"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(get_list_results(response)), 0)

    def test_coach_task_filtering_cannot_escape_rbac_scope(self):
        self.authenticate(self.coach_one)

        response = self.client.get(
            reverse("task-list"),
            {"client_ids": f"{self.client_one.id},{self.client_two.id}"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = get_list_results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.client_one_task.id)

    def test_coach_filtering_cannot_escape_rbac_scope(self):
        self.authenticate(self.coach_one)

        response = self.client.get(
            reverse("event-list"),
            {"client_ids": f"{self.client_one.id},{self.client_two.id}"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(get_list_results(response)), 1)
        self.assertEqual(get_list_results(response)[0]["id"], self.client_one_event.id)

    def test_event_model_exposes_required_fields(self):
        self.authenticate(self.admin)

        response = self.client.get(reverse("event-detail", args=[self.client_one_event.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertSetEqual(
            {
                "title",
                "event_date",
                "start_time",
                "end_time",
                "location",
                "description",
                "category",
                "client_name",
            },
            {
                "title",
                "event_date",
                "start_time",
                "end_time",
                "location",
                "description",
                "category",
                "client_name",
            },
        )
        for field_name in ["title", "event_date", "start_time", "end_time", "location", "description", "category", "client_name"]:
            self.assertIn(field_name, response.data)

    def test_client_can_create_recurring_event_for_self(self):
        self.authenticate(self.client_one)

        response = self.client.post(
            reverse("event-list"),
            {
                "title": "Recurring Check-in",
                "event_date": "2026-03-26",
                "start_time": "08:00:00",
                "end_time": "08:30:00",
                "location": "Home",
                "description": "Daily routine",
                "category": self.category.id,
                "client_id": self.client_one.id,
                "recurrence_type": "weekly",
                "recurrence_until": "2026-04-30",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["recurrence_type"], "weekly")
        self.assertEqual(response.data["client"]["id"], self.client_one.id)

    def test_admin_can_create_coach(self):
        self.authenticate(self.admin)

        response = self.client.post(
            reverse("admin-user-list"),
            {
                "username": "coach3",
                "password": "Pass12345!",
                "first_name": "Riley",
                "last_name": "Stone",
                "email": "coach3@example.com",
                "role": ROLE_COACH,
                "phone_number": "123-456-7890",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["role"], ROLE_COACH)

    def test_admin_can_create_client_with_assignment(self):
        self.authenticate(self.admin)

        response = self.client.post(
            reverse("admin-user-list"),
            {
                "username": "client4",
                "password": "Pass12345!",
                "first_name": "Jamie",
                "last_name": "Lane",
                "email": "client4@example.com",
                "role": ROLE_CLIENT,
                "assigned_coach_id": self.coach_one.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["role"], ROLE_CLIENT)
        self.assertEqual(response.data["assigned_coach_id"], self.coach_one.id)

    def test_admin_can_update_client_assignment(self):
        self.authenticate(self.admin)

        response = self.client.patch(
            reverse("admin-user-detail", args=[self.client_one.id]),
            {"assigned_coach_id": self.coach_two.id, "role": ROLE_CLIENT},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["assigned_coach_id"], self.coach_two.id)
        # Assert at the DB layer too — the response echoing the new coach is
        # not proof it persisted (see Item 3 of the July 2026 UX round).
        self.assertEqual(
            UserProfile.objects.get(user=self.client_one).assigned_coach_id,
            self.coach_two.id,
        )

    def test_admin_can_bulk_create_coaches_and_clients(self):
        self.authenticate(self.admin)

        response = self.client.post(
            reverse("admin-user-bulk-create"),
            [
                {
                    "username": "bulkcoach1",
                    "password": "Pass12345!",
                    "first_name": "Robin",
                    "last_name": "Coach",
                    "email": "bulkcoach1@example.com",
                    "role": ROLE_COACH,
                },
                {
                    "username": "bulkclient1",
                    "password": "Pass12345!",
                    "first_name": "Avery",
                    "last_name": "Client",
                    "email": "bulkclient1@example.com",
                    "role": ROLE_CLIENT,
                    "assigned_coach_id": self.coach_one.id,
                },
            ],
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]["role"], ROLE_COACH)
        self.assertEqual(response.data[1]["role"], ROLE_CLIENT)
        self.assertEqual(response.data[1]["assigned_coach_id"], self.coach_one.id)
        self.assertTrue(User.objects.filter(username="bulkcoach1").exists())
        self.assertTrue(User.objects.filter(username="bulkclient1").exists())

    def test_admin_bulk_create_is_atomic(self):
        self.authenticate(self.admin)

        response = self.client.post(
            reverse("admin-user-bulk-create"),
            [
                {
                    "username": "atomiccoach1",
                    "password": "Pass12345!",
                    "first_name": "Robin",
                    "last_name": "Coach",
                    "email": "atomiccoach1@example.com",
                    "role": ROLE_COACH,
                },
                {
                    "username": "atomicclient1",
                    "password": "Pass12345!",
                    "first_name": "Avery",
                    "last_name": "Client",
                    "email": "atomicclient1@example.com",
                    "role": ROLE_CLIENT,
                },
            ],
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(username="atomiccoach1").exists())
        self.assertFalse(User.objects.filter(username="atomicclient1").exists())

    def test_admin_can_import_users_from_csv(self):
        self.authenticate(self.admin)
        csv_file = SimpleUploadedFile(
            "users.csv",
            (
                "username,password,first_name,last_name,email,role,assigned_coach_id,phone_number\n"
                "csvcoach1,Pass12345!,Robin,Coach,csvcoach1@example.com,Coach,,555-1111\n"
                f"csvclient1,Pass12345!,Avery,Client,csvclient1@example.com,Client,{self.coach_one.id},555-2222\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("admin-user-import-csv"),
            {"file": csv_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]["role"], ROLE_COACH)
        self.assertEqual(response.data[1]["role"], ROLE_CLIENT)
        self.assertEqual(response.data[1]["assigned_coach_id"], self.coach_one.id)
        self.assertTrue(User.objects.filter(username="csvcoach1").exists())
        self.assertTrue(User.objects.filter(username="csvclient1").exists())

    def test_admin_csv_import_is_atomic(self):
        self.authenticate(self.admin)
        csv_file = SimpleUploadedFile(
            "invalid-users.csv",
            (
                "username,password,first_name,last_name,email,role,assigned_coach_id\n"
                "csvatomiccoach,Pass12345!,Robin,Coach,csvatomiccoach@example.com,Coach,\n"
                "csvatomicclient,Pass12345!,Avery,Client,csvatomicclient@example.com,Client,\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("admin-user-import-csv"),
            {"file": csv_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(username="csvatomiccoach").exists())
        self.assertFalse(User.objects.filter(username="csvatomicclient").exists())

    def test_admin_can_delete_client(self):
        removable_client = User.objects.create_user(username="client-delete", password="Pass12345!")
        removable_client.groups.add(self.client_group)
        removable_client.profile.assigned_coach = self.coach_one
        removable_client.profile.save()

        self.authenticate(self.admin)
        response = self.client.delete(reverse("admin-user-detail", args=[removable_client.id]))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(id=removable_client.id).exists())

    def test_non_admin_cannot_access_admin_user_management(self):
        self.authenticate(self.coach_one)

        response = self.client.get(reverse("admin-user-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_admin_cannot_bulk_create_admin_users(self):
        self.authenticate(self.coach_one)

        response = self.client.post(
            reverse("admin-user-bulk-create"),
            [
                {
                    "username": "blockedbulkuser",
                    "password": "Pass12345!",
                    "first_name": "Blocked",
                    "last_name": "User",
                    "email": "blocked@example.com",
                    "role": ROLE_COACH,
                }
            ],
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_admin_cannot_import_admin_users_from_csv(self):
        self.authenticate(self.coach_one)
        csv_file = SimpleUploadedFile(
            "blocked-users.csv",
            "username,password,role\nblockedcsv,Pass12345!,Coach\n".encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("admin-user-import-csv"),
            {"file": csv_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_access_analytics(self):
        self.authenticate(self.admin)

        response = self.client.get(reverse("admin-analytics"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("task_completion", response.data)
        self.assertIn("events_per_day", response.data)
        self.assertIn("events_per_month", response.data)
        self.assertEqual(response.data["task_completion"][0]["completed_on_time"], 1)

    def test_non_admin_cannot_access_analytics(self):
        self.authenticate(self.client_one)

        response = self.client.get(reverse("admin-analytics"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_superuser_is_treated_as_admin_for_admin_endpoints(self):
        superuser = User.objects.create_superuser(
            username="rootadmin",
            email="root@example.com",
            password="Pass12345!",
        )

        self.authenticate(superuser)

        response = self.client.get(reverse("admin-user-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_task_model_exposes_required_fields(self):
        self.authenticate(self.admin)

        response = self.client.get(reverse("task-detail", args=[self.client_one_task.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for field_name in ["title", "deadline", "description"]:
            self.assertIn(field_name, response.data)

    def test_category_is_only_linked_to_events(self):
        self.assertTrue(hasattr(self.client_one_event, "category"))
        self.assertFalse(hasattr(self.client_one_task, "category"))

    def test_client_can_reorder_own_tasks(self):
        self.authenticate(self.client_one)
        response = self.client.post(
            reverse("task-reorder"),
            {"items": [{"id": self.client_one_task.id, "priority": "high", "sort_order": 3}]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client_one_task.refresh_from_db()
        self.assertEqual(self.client_one_task.priority, "high")
        self.assertEqual(self.client_one_task.sort_order, 3)

    def test_reorder_ignores_out_of_scope_tasks(self):
        # client_one cannot reorder client_two's task; it should be silently ignored.
        self.authenticate(self.client_one)
        response = self.client.post(
            reverse("task-reorder"),
            {"items": [{"id": self.client_two_task.id, "priority": "high", "sort_order": 9}]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["updated"], 0)
        self.client_two_task.refresh_from_db()
        self.assertNotEqual(self.client_two_task.sort_order, 9)

    def test_client_can_create_category_for_self(self):
        self.authenticate(self.client_one)

        response = self.client.post(
            reverse("category-list"),
            {"name": "Focus", "color": "rose"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["client_id"], self.client_one.id)

    def test_coach_can_only_view_categories_for_assigned_clients(self):
        self.authenticate(self.coach_one)

        response = self.client.get(reverse("category-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(get_list_results(response)), 1)
        self.assertEqual(get_list_results(response)[0]["id"], self.category.id)

    def test_coach_can_create_category_for_assigned_client(self):
        self.authenticate(self.coach_one)

        response = self.client.post(
            reverse("category-list"),
            {"name": "Coach-made", "color": "rose", "client_id": self.client_one.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["client_id"], self.client_one.id)

    def test_coach_cannot_create_category_for_unassigned_client(self):
        self.authenticate(self.coach_one)

        response = self.client.post(
            reverse("category-list"),
            {"name": "Sneaky", "color": "rose", "client_id": self.client_two.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_coach_must_specify_client_id_to_create_category(self):
        self.authenticate(self.coach_one)

        response = self.client.post(
            reverse("category-list"),
            {"name": "Coach-made", "color": "rose"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_can_create_category_for_any_client(self):
        self.authenticate(self.admin)

        response = self.client.post(
            reverse("category-list"),
            {"name": "Admin-made", "color": "rose", "client_id": self.client_two.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["client_id"], self.client_two.id)

    def test_coach_can_delete_category_for_assigned_client(self):
        from planner.models import EventCategory

        # Create an unused category to avoid PROTECT on existing events
        cat = EventCategory.objects.create(name="Deletable", color="rose", client=self.client_one)
        self.authenticate(self.coach_one)

        response = self.client.delete(reverse("category-detail", args=[cat.id]))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_coach_cannot_delete_category_for_unassigned_client(self):
        # Create a category owned by client_two (assigned to coach_two)
        from planner.models import EventCategory

        other = EventCategory.objects.create(name="Other", color="rose", client=self.client_two)
        self.authenticate(self.coach_one)

        response = self.client.delete(reverse("category-detail", args=[other.id]))

        # 404 because the coach can't see it in the first place (queryset scope), which is fine.
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    def test_task_list_is_paginated_for_large_datasets(self):
        for index in range(12):
            Task.objects.create(
                title=f"Extra Task {index}",
                deadline=timezone.make_aware(datetime(2026, 3, 24, 12, index % 60)),
                description="Bulk pagination test",
                client=self.client_one,
            )

        self.authenticate(self.admin)
        response = self.client.get(reverse("task-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertEqual(len(response.data["results"]), 10)
        self.assertEqual(response.data["count"], 14)

    def test_admin_user_list_is_paginated_for_large_datasets(self):
        for index in range(12):
            extra_client = User.objects.create_user(username=f"bulkclient{index}", password="Pass12345!")
            extra_client.groups.add(self.client_group)
            extra_client.profile.assigned_coach = self.coach_one
            extra_client.profile.save()

        self.authenticate(self.admin)
        response = self.client.get(reverse("admin-user-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertEqual(len(response.data["results"]), 10)
        self.assertGreaterEqual(response.data["count"], 14)

    def test_client_cannot_use_category_from_another_client(self):
        self.authenticate(self.admin)

        response = self.client.post(
            reverse("event-list"),
            {
                "title": "Mismatch Category",
                "event_date": "2026-03-25",
                "start_time": "09:00:00",
                "end_time": "10:00:00",
                "location": "Remote",
                "description": "Should fail",
                "category": self.category_two.id,
                "client_id": self.client_one.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("category", response.data)

    def test_cannot_create_event_for_client_without_assigned_coach(self):
        unassigned_client = User.objects.create_user(username="client3", password="Pass12345!")
        unassigned_client.groups.add(self.client_group)

        self.authenticate(self.admin)
        response = self.client.post(
            reverse("event-list"),
            {
                "title": "Unassigned Event",
                "event_date": "2026-03-24",
                "start_time": "09:00:00",
                "end_time": "10:00:00",
                "location": "Remote",
                "description": "Should fail",
                "category": self.category.id,
                "client_id": unassigned_client.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("client_id", response.data)


ZOOM_ENV = {
    "ZOOM_ACCOUNT_ID": "test-account",
    "ZOOM_CLIENT_ID": "test-client-id",
    "ZOOM_CLIENT_SECRET": "test-client-secret",
}


def make_zoom_response(status_code=200, payload=None):
    response = mock.Mock()
    response.status_code = status_code
    response.json.return_value = payload if payload is not None else {}
    response.text = str(payload or "")
    return response


class ZoomEventLifecycleTests(APITestCase):
    """Zoom calls are mocked at the HTTP layer (planner.zoom.requests); no network."""

    @classmethod
    def setUpTestData(cls):
        cls.coach_group = Group.objects.get(name=ROLE_COACH)
        cls.client_group = Group.objects.get(name=ROLE_CLIENT)

        cls.coach = User.objects.create_user(username="zoomcoach", password="Pass12345!", first_name="Casey")
        cls.coach.groups.add(cls.coach_group)
        cls.coach.profile.zoom_user_email = "coach@zoom.example.com"
        cls.coach.profile.save()

        cls.other_coach = User.objects.create_user(username="zoomcoach2", password="Pass12345!")
        cls.other_coach.groups.add(cls.coach_group)

        cls.client_user = User.objects.create_user(username="zoomclient", password="Pass12345!", first_name="Jordan")
        cls.client_user.groups.add(cls.client_group)
        cls.client_user.profile.assigned_coach = cls.coach
        cls.client_user.profile.save()

        cls.other_client = User.objects.create_user(username="zoomclient2", password="Pass12345!")
        cls.other_client.groups.add(cls.client_group)
        cls.other_client.profile.assigned_coach = cls.other_coach
        cls.other_client.profile.save()

        cls.category = EventCategory.objects.create(name="Coaching", color="sky", client=cls.client_user)
        cls.other_category = EventCategory.objects.create(name="Other", color="rose", client=cls.other_client)

    def setUp(self):
        # The module caches the OAuth token in-process; isolate tests from each other.
        zoom._token_cache["access_token"] = None
        zoom._token_cache["expires_at"] = 0.0

    def authenticate(self, user):
        response = self.client.post(
            reverse("login"),
            {"username": user.username, "password": "Pass12345!"},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def event_payload(self, **overrides):
        payload = {
            "title": "Zoom Check-in",
            "event_date": "2026-08-03",
            "start_time": "09:00:00",
            "end_time": "10:00:00",
            "category": self.category.id,
            "client_id": self.client_user.id,
        }
        payload.update(overrides)
        return payload

    def mock_zoom_success(self, zoom_requests, meeting_id=98765, join_url="https://zoom.us/j/98765"):
        zoom_requests.post.return_value = make_zoom_response(200, {"access_token": "tok", "expires_in": 3600})
        zoom_requests.request.return_value = make_zoom_response(201, {"id": meeting_id, "join_url": join_url})

    @mock.patch.dict(os.environ, ZOOM_ENV)
    @mock.patch("planner.zoom.requests")
    def test_create_with_flag_creates_meeting_hosted_by_assigned_coach(self, zoom_requests):
        self.mock_zoom_success(zoom_requests)
        self.authenticate(self.coach)

        response = self.client.post(
            reverse("event-list"),
            self.event_payload(create_zoom_meeting=True),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["zoom_status"], "ok")
        self.assertEqual(response.data["zoom_meeting_id"], 98765)
        self.assertEqual(response.data["meeting_link"], "https://zoom.us/j/98765")

        event = Event.objects.get(pk=response.data["id"])
        self.assertEqual(event.zoom_meeting_id, 98765)
        self.assertEqual(event.meeting_link, "https://zoom.us/j/98765")

        method, url = zoom_requests.request.call_args[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, f"{zoom.ZOOM_API_BASE}/users/coach@zoom.example.com/meetings")
        body = zoom_requests.request.call_args[1]["json"]
        self.assertEqual(body["topic"], "Zoom Check-in")
        self.assertEqual(body["start_time"], "2026-08-03T09:00:00")
        self.assertEqual(body["duration"], 60)
        self.assertEqual(
            body["settings"],
            {
                "waiting_room": False,
                "join_before_host": True,
                "mute_upon_entry": False,
                "auto_recording": "cloud",
            },
        )

    @mock.patch.dict(os.environ, ZOOM_ENV)
    @mock.patch("planner.zoom.requests")
    def test_client_can_request_zoom_meeting_for_own_event(self, zoom_requests):
        self.mock_zoom_success(zoom_requests)
        self.authenticate(self.client_user)

        response = self.client.post(
            reverse("event-list"),
            self.event_payload(create_zoom_meeting=True),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["zoom_status"], "ok")
        _, url = zoom_requests.request.call_args[0]
        self.assertEqual(url, f"{zoom.ZOOM_API_BASE}/users/coach@zoom.example.com/meetings")

    @mock.patch.dict(os.environ, ZOOM_ENV)
    @mock.patch("planner.zoom.requests")
    def test_create_without_flag_never_calls_zoom(self, zoom_requests):
        self.authenticate(self.coach)

        response = self.client.post(reverse("event-list"), self.event_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data["zoom_status"])
        self.assertIsNone(response.data["zoom_meeting_id"])
        zoom_requests.post.assert_not_called()
        zoom_requests.request.assert_not_called()

    @mock.patch.dict(os.environ, ZOOM_ENV)
    @mock.patch("planner.zoom.requests")
    def test_zoom_failure_still_saves_event(self, zoom_requests):
        zoom_requests.post.side_effect = requests.ConnectionError("zoom is down")
        self.authenticate(self.coach)

        response = self.client.post(
            reverse("event-list"),
            self.event_payload(create_zoom_meeting=True),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["zoom_status"], "failed")
        self.assertIsNone(response.data["zoom_meeting_id"])
        self.assertEqual(response.data["meeting_link"], "")
        self.assertTrue(Event.objects.filter(pk=response.data["id"]).exists())

    @mock.patch("planner.zoom.requests")
    def test_zoom_not_configured_still_saves_event(self, zoom_requests):
        # No ZOOM_* env vars: the service raises ZoomNotConfigured and the write succeeds.
        env_without_zoom = {key: value for key, value in os.environ.items() if not key.startswith("ZOOM_")}
        self.authenticate(self.coach)

        with mock.patch.dict(os.environ, env_without_zoom, clear=True):
            response = self.client.post(
                reverse("event-list"),
                self.event_payload(create_zoom_meeting=True),
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["zoom_status"], "failed")
        self.assertTrue(Event.objects.filter(pk=response.data["id"]).exists())
        zoom_requests.post.assert_not_called()
        zoom_requests.request.assert_not_called()

    @mock.patch.dict(os.environ, ZOOM_ENV)
    @mock.patch("planner.zoom.requests")
    def test_missing_host_email_fails_zoom_but_saves_event(self, zoom_requests):
        self.authenticate(self.other_coach)  # neither this coach nor their client has a Zoom email

        response = self.client.post(
            reverse("event-list"),
            self.event_payload(
                create_zoom_meeting=True,
                category=self.other_category.id,
                client_id=self.other_client.id,
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["zoom_status"], "failed")
        zoom_requests.request.assert_not_called()

    @mock.patch.dict(os.environ, ZOOM_ENV)
    @mock.patch("planner.zoom.requests")
    def test_schedule_update_propagates_to_zoom(self, zoom_requests):
        self.mock_zoom_success(zoom_requests)
        event = Event.objects.create(
            title="Existing Session",
            event_date=date(2026, 8, 4),
            start_time=time(9, 0),
            end_time=time(10, 0),
            category=self.category,
            client=self.client_user,
            zoom_meeting_id=44444,
        )
        self.authenticate(self.coach)

        response = self.client.patch(
            reverse("event-detail", args=[event.id]),
            {"start_time": "11:00:00", "end_time": "11:45:00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["zoom_status"], "ok")
        method, url = zoom_requests.request.call_args[0]
        self.assertEqual(method, "PATCH")
        self.assertEqual(url, f"{zoom.ZOOM_API_BASE}/meetings/44444")
        body = zoom_requests.request.call_args[1]["json"]
        self.assertEqual(body["start_time"], "2026-08-04T11:00:00")
        self.assertEqual(body["duration"], 45)

    @mock.patch.dict(os.environ, ZOOM_ENV)
    @mock.patch("planner.zoom.requests")
    def test_non_schedule_update_does_not_call_zoom(self, zoom_requests):
        event = Event.objects.create(
            title="Existing Session",
            event_date=date(2026, 8, 4),
            start_time=time(9, 0),
            end_time=time(10, 0),
            category=self.category,
            client=self.client_user,
            zoom_meeting_id=44444,
        )
        self.authenticate(self.coach)

        response = self.client.patch(
            reverse("event-detail", args=[event.id]),
            {"title": "Renamed Session"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["zoom_status"])
        zoom_requests.request.assert_not_called()

    @mock.patch.dict(os.environ, ZOOM_ENV)
    @mock.patch("planner.zoom.requests")
    def test_zoom_failure_on_update_still_saves_changes(self, zoom_requests):
        zoom_requests.post.side_effect = requests.Timeout("token timeout")
        event = Event.objects.create(
            title="Existing Session",
            event_date=date(2026, 8, 4),
            start_time=time(9, 0),
            end_time=time(10, 0),
            category=self.category,
            client=self.client_user,
            zoom_meeting_id=44444,
        )
        self.authenticate(self.coach)

        response = self.client.patch(
            reverse("event-detail", args=[event.id]),
            {"start_time": "11:00:00", "end_time": "12:00:00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["zoom_status"], "failed")
        event.refresh_from_db()
        self.assertEqual(event.start_time, time(11, 0))

    @mock.patch.dict(os.environ, ZOOM_ENV)
    @mock.patch("planner.zoom.requests")
    def test_destroy_deletes_zoom_meeting(self, zoom_requests):
        zoom_requests.post.return_value = make_zoom_response(200, {"access_token": "tok", "expires_in": 3600})
        zoom_requests.request.return_value = make_zoom_response(204)
        event = Event.objects.create(
            title="Doomed Session",
            event_date=date(2026, 8, 5),
            start_time=time(9, 0),
            end_time=time(10, 0),
            category=self.category,
            client=self.client_user,
            zoom_meeting_id=55555,
        )
        self.authenticate(self.coach)

        response = self.client.delete(reverse("event-detail", args=[event.id]))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Event.objects.filter(pk=event.id).exists())
        method, url = zoom_requests.request.call_args[0]
        self.assertEqual(method, "DELETE")
        self.assertEqual(url, f"{zoom.ZOOM_API_BASE}/meetings/55555")

    @mock.patch.dict(os.environ, ZOOM_ENV)
    @mock.patch("planner.zoom.requests")
    def test_destroy_tolerates_zoom_404(self, zoom_requests):
        zoom_requests.post.return_value = make_zoom_response(200, {"access_token": "tok", "expires_in": 3600})
        zoom_requests.request.return_value = make_zoom_response(404, {"code": 3001, "message": "Meeting does not exist"})
        event = Event.objects.create(
            title="Already Gone",
            event_date=date(2026, 8, 5),
            start_time=time(9, 0),
            end_time=time(10, 0),
            category=self.category,
            client=self.client_user,
            zoom_meeting_id=66666,
        )
        self.authenticate(self.coach)

        response = self.client.delete(reverse("event-detail", args=[event.id]))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Event.objects.filter(pk=event.id).exists())

    @mock.patch.dict(os.environ, ZOOM_ENV)
    @mock.patch("planner.zoom.requests")
    def test_token_is_cached_across_calls(self, zoom_requests):
        self.mock_zoom_success(zoom_requests)
        self.authenticate(self.coach)

        for index in range(2):
            response = self.client.post(
                reverse("event-list"),
                self.event_payload(title=f"Session {index}", create_zoom_meeting=True),
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertEqual(zoom_requests.post.call_count, 1)
        self.assertEqual(zoom_requests.request.call_count, 2)

    @mock.patch.dict(os.environ, ZOOM_ENV)
    @mock.patch("planner.zoom.requests")
    def test_zoom_flag_does_not_bypass_rbac(self, zoom_requests):
        self.mock_zoom_success(zoom_requests)
        self.authenticate(self.coach)  # not other_client's coach

        response = self.client.post(
            reverse("event-list"),
            self.event_payload(
                create_zoom_meeting=True,
                category=self.other_category.id,
                client_id=self.other_client.id,
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        zoom_requests.request.assert_not_called()


class ExpandEventDatesTests(SimpleTestCase):
    """Pure expansion logic: recurrence types, until boundary, range clipping."""

    def test_non_recurring_returns_base_date(self):
        self.assertEqual(
            expand_event_dates(date(2026, 3, 20), "none", None),
            [date(2026, 3, 20)],
        )

    def test_non_recurring_outside_range_is_clipped(self):
        self.assertEqual(
            expand_event_dates(date(2026, 3, 20), "none", None, range_start=date(2026, 4, 1)),
            [],
        )

    def test_daily_includes_every_day_through_until(self):
        self.assertEqual(
            expand_event_dates(date(2026, 3, 20), "daily", date(2026, 3, 24)),
            [date(2026, 3, 20 + offset) for offset in range(5)],
        )

    def test_weekly_until_boundary_is_inclusive(self):
        self.assertEqual(
            expand_event_dates(date(2026, 3, 20), "weekly", date(2026, 4, 3)),
            [date(2026, 3, 20), date(2026, 3, 27), date(2026, 4, 3)],
        )

    def test_weekly_until_between_occurrences_stops_before_it(self):
        self.assertEqual(
            expand_event_dates(date(2026, 3, 20), "weekly", date(2026, 4, 9)),
            [date(2026, 3, 20), date(2026, 3, 27), date(2026, 4, 3)],
        )

    def test_monthly_repeats_on_same_day_of_month(self):
        self.assertEqual(
            expand_event_dates(date(2026, 1, 15), "monthly", date(2026, 4, 15)),
            [date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15), date(2026, 4, 15)],
        )

    def test_monthly_skips_months_without_the_day(self):
        self.assertEqual(
            expand_event_dates(date(2026, 1, 31), "monthly", date(2026, 5, 31)),
            [date(2026, 1, 31), date(2026, 3, 31), date(2026, 5, 31)],
        )

    def test_range_clips_daily_expansion(self):
        self.assertEqual(
            expand_event_dates(
                date(2026, 3, 20),
                "daily",
                date(2026, 3, 31),
                range_start=date(2026, 3, 22),
                range_end=date(2026, 3, 23),
            ),
            [date(2026, 3, 22), date(2026, 3, 23)],
        )

    def test_range_after_until_yields_nothing(self):
        self.assertEqual(
            expand_event_dates(
                date(2026, 3, 20),
                "daily",
                date(2026, 3, 24),
                range_start=date(2026, 4, 1),
            ),
            [],
        )


class RecurringEventExpansionTests(APITestCase):
    """The events list expands recurring events into per-occurrence entries."""

    @classmethod
    def setUpTestData(cls):
        coach_group = Group.objects.get(name=ROLE_COACH)
        client_group = Group.objects.get(name=ROLE_CLIENT)

        cls.coach = User.objects.create_user(username="reccoach", password="Pass12345!")
        cls.coach.groups.add(coach_group)

        cls.client_user = User.objects.create_user(username="recclient", password="Pass12345!")
        cls.client_user.groups.add(client_group)
        cls.client_user.profile.assigned_coach = cls.coach
        cls.client_user.profile.save()

        cls.category = EventCategory.objects.create(name="Routine", color="emerald", client=cls.client_user)

        cls.daily_event = Event.objects.create(
            title="Morning Walk",
            event_date=date(2026, 6, 1),
            start_time=time(7, 0),
            end_time=time(7, 30),
            category=cls.category,
            client=cls.client_user,
            recurrence_type="daily",
            recurrence_until=date(2026, 6, 4),
        )
        cls.single_event = Event.objects.create(
            title="One-off Session",
            event_date=date(2026, 6, 10),
            start_time=time(9, 0),
            end_time=time(10, 0),
            category=cls.category,
            client=cls.client_user,
        )
        cls.zoom_event = Event.objects.create(
            title="Weekly Zoom Check-in",
            event_date=date(2026, 6, 3),
            start_time=time(11, 0),
            end_time=time(11, 30),
            category=cls.category,
            client=cls.client_user,
            recurrence_type="weekly",
            recurrence_until=date(2026, 6, 17),
            meeting_link="https://zoom.us/j/424242",
            zoom_meeting_id=424242,
        )

    def authenticate(self, user):
        response = self.client.post(
            reverse("login"),
            {"username": user.username, "password": "Pass12345!"},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def fetch_rows(self, params=None):
        response = self.client.get(reverse("event-list"), params or {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return get_list_results(response)

    def rows_for(self, rows, event):
        return [row for row in rows if row["id"] == event.id]

    def test_daily_event_appears_on_every_day_through_until(self):
        self.authenticate(self.client_user)
        rows = self.rows_for(self.fetch_rows(), self.daily_event)
        self.assertEqual(
            [row["event_date"] for row in rows],
            ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04"],
        )

    def test_weekly_occurrences_share_id_and_meeting_link(self):
        self.authenticate(self.client_user)
        with mock.patch("planner.zoom.requests") as zoom_requests:
            rows = self.rows_for(self.fetch_rows(), self.zoom_event)
        self.assertEqual(
            [row["event_date"] for row in rows],
            ["2026-06-03", "2026-06-10", "2026-06-17"],
        )
        for row in rows:
            self.assertEqual(row["meeting_link"], "https://zoom.us/j/424242")
            self.assertEqual(row["zoom_meeting_id"], 424242)
        # Rendering occurrences must never talk to Zoom.
        zoom_requests.post.assert_not_called()
        zoom_requests.request.assert_not_called()

    def test_list_is_ordered_by_date_and_start_time(self):
        self.authenticate(self.client_user)
        rows = self.fetch_rows()
        keys = [(row["event_date"], row["start_time"]) for row in rows]
        self.assertEqual(keys, sorted(keys))

    def test_range_params_clip_expansion_and_base_events(self):
        self.authenticate(self.client_user)
        rows = self.fetch_rows({"start": "2026-06-02", "end": "2026-06-10"})
        self.assertEqual(
            [row["event_date"] for row in self.rows_for(rows, self.daily_event)],
            ["2026-06-02", "2026-06-03", "2026-06-04"],
        )
        self.assertEqual(
            [row["event_date"] for row in self.rows_for(rows, self.zoom_event)],
            ["2026-06-03", "2026-06-10"],
        )
        # Non-recurring event inside the range stays; outside it disappears.
        self.assertEqual(len(self.rows_for(rows, self.single_event)), 1)
        clipped = self.fetch_rows({"end": "2026-06-05"})
        self.assertEqual(self.rows_for(clipped, self.single_event), [])

    def test_invalid_range_param_is_rejected(self):
        self.authenticate(self.client_user)
        response = self.client.get(reverse("event-list"), {"start": "not-a-date"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("start", response.data)

    def test_editing_any_occurrence_edits_the_underlying_event(self):
        self.authenticate(self.client_user)
        response = self.client.patch(
            reverse("event-detail", args=[self.daily_event.id]),
            {"title": "Evening Walk"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = self.rows_for(self.fetch_rows(), self.daily_event)
        self.assertEqual(len(rows), 4)
        for row in rows:
            self.assertEqual(row["title"], "Evening Walk")


class CoachRoleChangeGuardTests(APITestCase):
    """Role change away from Coach is blocked while clients remain assigned."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username="admin9", password="Pass12345!")
        cls.admin.groups.add(Group.objects.get(name=ROLE_ADMIN))
        cls.coach = User.objects.create_user(username="coach9", password="Pass12345!")
        cls.coach.groups.add(Group.objects.get(name=ROLE_COACH))
        cls.other_coach = User.objects.create_user(username="coach10", password="Pass12345!")
        cls.other_coach.groups.add(Group.objects.get(name=ROLE_COACH))
        cls.client_user = User.objects.create_user(username="client9", password="Pass12345!")
        cls.client_user.groups.add(Group.objects.get(name=ROLE_CLIENT))
        cls.client_user.profile.assigned_coach = cls.coach
        cls.client_user.profile.save()

    def _auth(self):
        self.client.force_authenticate(self.admin)

    def test_role_flip_blocked_while_clients_assigned(self):
        self._auth()
        resp = self.client.patch(
            f"/api/admin/users/{self.coach.id}/",
            {"role": ROLE_CLIENT, "assigned_coach_id": self.other_coach.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("role", resp.data)
        self.coach.refresh_from_db()
        self.assertTrue(self.coach.groups.filter(name=ROLE_COACH).exists())

    def test_role_flip_allowed_after_reassignment(self):
        self._auth()
        self.client_user.profile.assigned_coach = self.other_coach
        self.client_user.profile.save()
        resp = self.client.patch(
            f"/api/admin/users/{self.coach.id}/",
            {"role": ROLE_CLIENT, "assigned_coach_id": self.other_coach.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
