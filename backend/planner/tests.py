from datetime import date, datetime, time

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.constants import ROLE_ADMIN, ROLE_CLIENT, ROLE_COACH

from .models import Event, EventCategory, Task


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
