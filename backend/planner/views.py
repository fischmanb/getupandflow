import csv
import io

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, F, Q
from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from accounts.constants import ROLE_ADMIN, ROLE_CLIENT, ROLE_COACH
from accounts.models import UserProfile

from .models import Event, EventCategory, Task
from .pagination import StandardResultsSetPagination
from .permissions import RBACScope
from .serializers import (
    AdminManagedUserSerializer,
    AdminManagedUserCSVImportSerializer,
    AnalyticsSummarySerializer,
    ClientAssignmentSerializer,
    EventCategorySerializer,
    EventSerializer,
    TaskSerializer,
    UserSummarySerializer,
)


class AdminOrReadOnlyForAuthenticated(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        return request.user and request.user.is_authenticated and RBACScope.is_admin(request.user)


class AdminOnlyPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and RBACScope.is_admin(request.user)


class ClientCategoryPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        return request.user and request.user.is_authenticated and RBACScope.is_client(request.user)

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return RBACScope.is_client(request.user) and obj.client_id == request.user.id


class RoleScopedQuerysetMixin:
    client_field = "client"

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        role = RBACScope.role_for(user)

        if role == ROLE_ADMIN:
            scoped = queryset
        elif role == ROLE_CLIENT:
            scoped = queryset.filter(**{self.client_field: user})
        elif role == ROLE_COACH:
            scoped = queryset.filter(**{f"{self.client_field}__profile__assigned_coach": user})
        else:
            return queryset.none()

        return self._apply_client_ids_filter(scoped)

    def _apply_client_ids_filter(self, queryset):
        raw_client_ids = self.request.query_params.get("client_ids")
        if not raw_client_ids:
            return queryset

        client_ids = []
        for value in raw_client_ids.split(","):
            value = value.strip()
            if value.isdigit():
                client_ids.append(int(value))

        if not client_ids:
            return queryset.none()

        return queryset.filter(**{f"{self.client_field}__in": client_ids})


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UserSummarySerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        role = RBACScope.role_for(user)

        if role == ROLE_ADMIN:
            queryset = User.objects.all().order_by("username")
            raw_role = self.request.query_params.get("role")
            if raw_role in {ROLE_ADMIN, ROLE_COACH, ROLE_CLIENT}:
                queryset = queryset.filter(groups__name=raw_role)
            return queryset
        if role == ROLE_COACH:
            return User.objects.filter(profile__assigned_coach=user).order_by("username")
        if role == ROLE_CLIENT:
            return User.objects.filter(id=user.id)
        return User.objects.none()


class ClientAssignmentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ClientAssignmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        role = RBACScope.role_for(user)
        queryset = UserProfile.objects.select_related("user", "assigned_coach").order_by("user__username")

        if role == ROLE_ADMIN:
            return queryset.filter(user__groups__name=ROLE_CLIENT)
        if role == ROLE_COACH:
            return queryset.filter(user__groups__name=ROLE_CLIENT, assigned_coach=user)
        if role == ROLE_CLIENT:
            return queryset.filter(user=user)
        return queryset.none()


class EventCategoryViewSet(viewsets.ModelViewSet):
    queryset = EventCategory.objects.select_related("client").order_by("name", "id")
    serializer_class = EventCategorySerializer
    permission_classes = [ClientCategoryPermission]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        if RBACScope.is_admin(user):
            queryset = queryset
        elif RBACScope.is_coach(user):
            queryset = queryset.filter(client__profile__assigned_coach=user)
        elif RBACScope.is_client(user):
            queryset = queryset.filter(client=user)
        else:
            return queryset.none()

        raw_client_id = self.request.query_params.get("client_id")
        if raw_client_id and raw_client_id.isdigit():
            queryset = queryset.filter(client_id=int(raw_client_id))
        return queryset

    def perform_create(self, serializer):
        serializer.save(client=self.request.user)


class EventViewSet(RoleScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Event.objects.select_related("client", "client__profile", "category").all()
    serializer_class = EventSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None


class TaskViewSet(RoleScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Task.objects.select_related("client", "client__profile").order_by("deadline", "id")
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination


class AdminManagedUserViewSet(viewsets.ModelViewSet):
    serializer_class = AdminManagedUserSerializer
    permission_classes = [AdminOnlyPermission]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = User.objects.select_related("profile").filter(
            groups__name__in=[ROLE_COACH, ROLE_CLIENT]
        ).order_by("username").distinct()
        raw_role = self.request.query_params.get("role")
        if raw_role in {ROLE_COACH, ROLE_CLIENT}:
            queryset = queryset.filter(groups__name=raw_role)
        return queryset

    def perform_destroy(self, instance):
        if instance.groups.filter(name=ROLE_COACH).exists() and instance.coached_clients.exists():
            raise ValidationError({"assigned_coach_id": "Reassign this coach's clients before deleting the coach."})
        instance.delete()

    def _normalize_csv_value(self, value):
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    def _build_csv_payload(self, uploaded_file):
        try:
            decoded_file = uploaded_file.read().decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValidationError({"file": "CSV file must be UTF-8 encoded."}) from exc

        reader = csv.DictReader(io.StringIO(decoded_file))
        required_columns = {"username", "password", "role"}
        if not reader.fieldnames:
            raise ValidationError({"file": "CSV file must include a header row."})
        missing_columns = sorted(required_columns.difference(set(reader.fieldnames)))
        if missing_columns:
            raise ValidationError({"file": f"CSV file is missing required columns: {', '.join(missing_columns)}."})

        payload = []
        for index, row in enumerate(reader, start=2):
            normalized_row = {key: self._normalize_csv_value(value) for key, value in row.items()}
            if not any(normalized_row.values()):
                continue

            item = {
                "username": normalized_row.get("username"),
                "password": normalized_row.get("password"),
                "first_name": normalized_row.get("first_name") or "",
                "last_name": normalized_row.get("last_name") or "",
                "email": normalized_row.get("email") or "",
                "role": normalized_row.get("role"),
            }

            assigned_coach_id = normalized_row.get("assigned_coach_id")
            if assigned_coach_id is not None:
                item["assigned_coach_id"] = assigned_coach_id

            phone_number = normalized_row.get("phone_number")
            if phone_number is not None:
                item["phone_number"] = phone_number

            payload.append(item)

        if not payload:
            raise ValidationError({"file": "CSV file did not contain any user rows."})

        return payload

    @extend_schema(
        request=AdminManagedUserSerializer(many=True),
        responses={201: AdminManagedUserSerializer(many=True)},
    )
    @action(detail=False, methods=["post"], url_path="bulk")
    def bulk_create(self, request):
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            users = serializer.save()
        response_serializer = self.get_serializer(users, many=True)
        return Response(response_serializer.data, status=201)

    @extend_schema(
        request=AdminManagedUserCSVImportSerializer,
        responses={201: AdminManagedUserSerializer(many=True)},
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="import-csv",
        parser_classes=[MultiPartParser, FormParser],
    )
    def import_csv(self, request):
        upload_serializer = AdminManagedUserCSVImportSerializer(data=request.data)
        upload_serializer.is_valid(raise_exception=True)

        payload = self._build_csv_payload(upload_serializer.validated_data["file"])
        serializer = self.get_serializer(data=payload, many=True)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            users = serializer.save()

        response_serializer = self.get_serializer(users, many=True)
        return Response(response_serializer.data, status=201)


class AdminAnalyticsView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        now = timezone.now()
        task_completion_rows = (
            Task.objects.filter(client__groups__name=ROLE_CLIENT)
            .values("client_id")
            .annotate(client_name=F("client__username"))
            .annotate(
                total_tasks=Count("id"),
                completed_tasks=Count("id", filter=Q(completed_at__isnull=False)),
                completed_on_time=Count("id", filter=Q(completed_at__isnull=False, completed_at__lte=F("deadline"))),
                overdue_open_tasks=Count("id", filter=Q(completed_at__isnull=True, deadline__lt=now)),
            )
            .order_by("client_name")
        )
        events_per_day_map = {}
        events_per_month_map = {}
        for event_date in Event.objects.values_list("event_date", flat=True):
            day_key = event_date.isoformat()
            month_key = event_date.strftime("%Y-%m")
            events_per_day_map[day_key] = events_per_day_map.get(day_key, 0) + 1
            events_per_month_map[month_key] = events_per_month_map.get(month_key, 0) + 1

        serializer = AnalyticsSummarySerializer(
            {
                "task_completion": [
                    {
                        **row,
                        "completion_rate": round((row["completed_on_time"] / row["total_tasks"]) * 100, 1)
                        if row["total_tasks"]
                        else 0,
                    }
                    for row in task_completion_rows
                ],
                "events_per_day": [
                    {"date": key, "count": events_per_day_map[key]}
                    for key in sorted(events_per_day_map.keys())
                ],
                "events_per_month": [
                    {"month": key, "count": events_per_month_map[key]}
                    for key in sorted(events_per_month_map.keys())
                ],
            }
        )
        return Response(serializer.data)
