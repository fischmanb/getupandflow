import csv
import io
import logging
from datetime import datetime, timedelta

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, F, Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from accounts.constants import ROLE_ADMIN, ROLE_CLIENT, ROLE_COACH
from accounts.models import UserProfile
from billing.permissions import ClientOnlyPermission
from notifications.emails import (
    send_panic_booked_client_email,
    send_panic_booked_coach_email,
    send_panic_cancelled_coach_email,
)
from notifications.ntfy import notify_panic_booked

from . import panic, zoom
from .models import Event, EventCategory, Task
from .pagination import StandardResultsSetPagination
from .recurrence import expand_event_dates
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

logger = logging.getLogger(__name__)


class AdminOrReadOnlyForAuthenticated(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        return request.user and request.user.is_authenticated and RBACScope.is_admin(request.user)


class AdminOnlyPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and RBACScope.is_admin(request.user)


class ClientCategoryPermission(permissions.BasePermission):
    """Categories belong to a Client. The Client, their assigned Coach, and any Admin
    may create/edit/delete on the Client's behalf. Anyone authenticated may read
    within their RBAC scope (queryset already enforces that).
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return (
            RBACScope.is_admin(request.user)
            or RBACScope.is_coach(request.user)
            or RBACScope.is_client(request.user)
        )

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        user = request.user
        if RBACScope.is_admin(user):
            return True
        if RBACScope.is_client(user):
            return obj.client_id == user.id
        if RBACScope.is_coach(user):
            return getattr(obj.client, "profile", None) and obj.client.profile.assigned_coach_id == user.id
        return False


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
        queryset = UserProfile.objects.select_related(
            "user", "assigned_coach", "assigned_coach__profile"
        ).order_by("user__username")

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
        # If the request didn't specify a client_id, default to "self if I'm a Client".
        # Coaches/Admins must pass client_id explicitly (validated in the serializer).
        if "client_id" not in serializer.validated_data:
            user = self.request.user
            if not RBACScope.is_client(user):
                raise ValidationError({"client_id": "Coaches and admins must specify a client."})
            serializer.save(client=user)
            return
        serializer.save()


class EventViewSet(RoleScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Event.objects.select_related("client", "client__profile", "category").all()
    serializer_class = EventSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    ZOOM_SCHEDULE_FIELDS = ("event_date", "start_time", "end_time")

    def list(self, request, *args, **kwargs):
        """Expand recurring events into one entry per occurrence.

        Each occurrence repeats the base event's payload (same id and
        meeting_link — it is one underlying event and one Zoom meeting) with
        only event_date swapped, so edits/deletes from any occurrence hit the
        single source of truth. Optional ?start=YYYY-MM-DD / ?end=YYYY-MM-DD
        clip the expansion to a visible range; without them, expansion is
        bounded by recurrence_until (required for recurring events).
        """
        range_start = self._parse_range_param(request, "start")
        range_end = self._parse_range_param(request, "end")
        events = list(self.filter_queryset(self.get_queryset()))
        serialized = self.get_serializer(events, many=True).data
        rows = []
        for event, row in zip(events, serialized):
            for day in expand_event_dates(
                event.event_date,
                event.recurrence_type,
                event.recurrence_until,
                range_start,
                range_end,
            ):
                rows.append(row if day == event.event_date else {**row, "event_date": day.isoformat()})
        # Keep the model's ordering contract across expanded occurrences.
        rows.sort(key=lambda item: (item["event_date"], item["start_time"], item["title"]))
        return Response(rows)

    @staticmethod
    def _parse_range_param(request, name):
        raw = request.query_params.get(name)
        if not raw:
            return None
        parsed = parse_date(raw)
        if parsed is None:
            raise ValidationError({name: "Enter a valid date (YYYY-MM-DD)."})
        return parsed

    def _resolve_zoom_host_email(self, event):
        """Host the meeting as the event owner's assigned coach; fall back to the
        requesting user's own Zoom email if they are a coach.
        """
        profile = getattr(event.client, "profile", None)
        coach = profile.assigned_coach if profile else None
        coach_profile = getattr(coach, "profile", None)
        if coach_profile and coach_profile.zoom_user_email:
            return coach_profile.zoom_user_email
        creator = self.request.user
        if RBACScope.is_coach(creator):
            creator_profile = getattr(creator, "profile", None)
            if creator_profile and creator_profile.zoom_user_email:
                return creator_profile.zoom_user_email
        return None

    def _create_zoom_meeting(self, event):
        # FAILURE RULE: a Zoom problem must never fail the event write.
        try:
            host_email = self._resolve_zoom_host_email(event)
            if not host_email:
                raise zoom.ZoomNotConfigured("No Zoom host email configured for this event's coach.")
            meeting = zoom.create_meeting(host_email, event)
            event.zoom_meeting_id = meeting["id"]
            event.meeting_link = meeting["join_url"]
            event.save()
            event._zoom_status = "ok"
        except Exception:
            logger.exception("Failed to create Zoom meeting for event %s", event.pk)
            event._zoom_status = "failed"

    def _update_zoom_meeting(self, event):
        try:
            zoom.update_meeting(event.zoom_meeting_id, event)
            event._zoom_status = "ok"
        except Exception:
            logger.exception("Failed to update Zoom meeting %s for event %s", event.zoom_meeting_id, event.pk)
            event._zoom_status = "failed"

    def perform_create(self, serializer):
        wants_zoom = serializer.validated_data.pop("create_zoom_meeting", False)
        event = serializer.save()
        if wants_zoom:
            self._create_zoom_meeting(event)

    def perform_update(self, serializer):
        wants_zoom = serializer.validated_data.pop("create_zoom_meeting", False)
        instance = serializer.instance
        schedule_changed = any(
            field in serializer.validated_data and serializer.validated_data[field] != getattr(instance, field)
            for field in self.ZOOM_SCHEDULE_FIELDS
        )
        event = serializer.save()
        if event.zoom_meeting_id is None:
            if wants_zoom:
                self._create_zoom_meeting(event)
        elif schedule_changed:
            self._update_zoom_meeting(event)

    def perform_destroy(self, instance):
        meeting_id = instance.zoom_meeting_id
        instance.delete()
        if meeting_id is None:
            return
        try:
            zoom.delete_meeting(meeting_id)
        except zoom.ZoomError as exc:
            if exc.status_code != 404:  # a meeting already gone in Zoom is fine
                logger.exception("Failed to delete Zoom meeting %s", meeting_id)
        except Exception:
            logger.exception("Failed to delete Zoom meeting %s", meeting_id)


class TaskViewSet(RoleScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Task.objects.select_related("client", "client__profile").order_by(
        "sort_order", "deadline", "id"
    )
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    @action(detail=False, methods=["post"], url_path="reorder")
    def reorder(self, request):
        """Persist drag-and-drop ordering. Body: {"items": [{"id", "priority", "sort_order"}, ...]}.
        Only tasks within the requester's RBAC scope are updated; others are ignored.
        """
        items = request.data.get("items", [])
        if not isinstance(items, list):
            raise ValidationError({"items": "Expected a list."})

        scoped = self.get_queryset()
        scoped_ids = set(scoped.values_list("id", flat=True))
        valid_priorities = {choice[0] for choice in Task.PRIORITY_CHOICES}

        to_update = []
        for item in items:
            task_id = item.get("id")
            if task_id not in scoped_ids:
                continue
            task = Task.objects.get(pk=task_id)
            if "priority" in item and item["priority"] in valid_priorities:
                task.priority = item["priority"]
            if "sort_order" in item:
                try:
                    task.sort_order = max(0, int(item["sort_order"]))
                except (TypeError, ValueError):
                    pass
            to_update.append(task)

        with transaction.atomic():
            for task in to_update:
                # Use update() to skip full_clean revalidation on bulk reorder.
                Task.objects.filter(pk=task.pk).update(
                    priority=task.priority, sort_order=task.sort_order
                )

        return Response({"updated": len(to_update)})


PANIC_UNASSIGNED_MESSAGE = (
    "We're still matching you with your coach — the Panic Button unlocks the moment they're in place."
)


def _serialize_panic_session(event, working_tz, display_tz, now):
    start = datetime.combine(event.event_date, event.start_time, tzinfo=working_tz)
    end = datetime.combine(event.event_date, event.end_time, tzinfo=working_tz)
    return {
        "id": event.id,
        "start_at": start.astimezone(display_tz).isoformat(),
        "end_at": end.astimezone(display_tz).isoformat(),
        "duration_minutes": int((end - start).total_seconds() // 60),
        "note": event.description,
        "meeting_link": event.meeting_link,
        "can_cancel": start > now,
    }


class PanicAvailabilityView(APIView):
    """Free panic-session start slots on the coach's calendar (client-self only).

    Slots are the complement of the coach's existing events over the booking
    window, intersected with the bookable-hours policy (panic.py), contiguity
    for the requested duration, and the client's remaining daily cap.
    """

    permission_classes = [permissions.IsAuthenticated, ClientOnlyPermission]

    @extend_schema(responses=None)
    def get(self, request):
        coach = request.user.profile.assigned_coach
        if coach is None:
            return Response({"detail": PANIC_UNASSIGNED_MESSAGE}, status=409)

        raw_duration = request.query_params.get("duration", str(min(panic.PANIC_DURATIONS)))
        try:
            duration = int(raw_duration)
        except (TypeError, ValueError):
            duration = 0
        if duration not in panic.PANIC_DURATIONS:
            return Response({"duration": "Panic sessions are 15 or 30 minutes."}, status=400)

        now = timezone.now()
        working_tz = panic.working_timezone_for(coach)
        display_tz = panic.display_timezone_for(request.user, working_tz)
        minutes_by_day = panic.panic_minutes_by_client_day(request.user, working_tz, display_tz)
        starts = panic.available_starts(coach, request.user, duration, now, minutes_by_day=minutes_by_day)

        # Group by the CLIENT's calendar day — day tabs render in their timezone.
        days = []
        for start in starts:
            local = start.astimezone(display_tz)
            day_key = local.date().isoformat()
            if not days or days[-1]["date"] != day_key:
                days.append({"date": day_key, "slots": []})
            days[-1]["slots"].append({"start_at": local.isoformat()})

        # When the window ∩ bookable-hours intersection is empty (e.g. Friday
        # evening), name the next moment booking opens (e.g. Monday morning).
        next_bookable_at = None
        if not starts:
            candidate = panic.next_policy_open_at(now, duration, working_tz)
            _, window_end = panic.booking_window(now)
            if candidate is not None and candidate > window_end:
                next_bookable_at = candidate.astimezone(display_tz).isoformat()

        today = now.astimezone(display_tz).date()
        return Response(
            {
                "duration": duration,
                "timezone": str(display_tz),
                "cap_minutes": panic.PANIC_DAILY_CAP_MINUTES,
                "remaining_minutes_today": panic.remaining_minutes_for_day(minutes_by_day, today),
                "days": days,
                "next_bookable_at": next_bookable_at,
            }
        )


class PanicSessionView(APIView):
    """Book (POST) and review (GET) the client's own panic sessions."""

    permission_classes = [permissions.IsAuthenticated, ClientOnlyPermission]

    @extend_schema(responses=None)
    def get(self, request):
        coach = request.user.profile.assigned_coach
        now = timezone.now()
        working_tz = panic.working_timezone_for(coach)
        display_tz = panic.display_timezone_for(request.user, working_tz)
        minutes_by_day = panic.panic_minutes_by_client_day(request.user, working_tz, display_tz)
        today = now.astimezone(display_tz).date()

        rows = [
            _serialize_panic_session(event, working_tz, display_tz, now)
            for event in Event.objects.filter(client=request.user, is_panic=True)
            if datetime.combine(event.event_date, event.start_time, tzinfo=working_tz)
            .astimezone(display_tz)
            .date()
            >= today
        ]
        rows.sort(key=lambda row: row["start_at"])
        return Response(
            {
                "timezone": str(display_tz),
                "cap_minutes": panic.PANIC_DAILY_CAP_MINUTES,
                "remaining_minutes_today": panic.remaining_minutes_for_day(minutes_by_day, today),
                "sessions": rows,
            }
        )

    @extend_schema(request=None, responses=None)
    def post(self, request):
        coach = request.user.profile.assigned_coach
        if coach is None:
            return Response({"detail": PANIC_UNASSIGNED_MESSAGE}, status=409)

        try:
            duration = int(request.data.get("duration"))
        except (TypeError, ValueError):
            duration = 0
        if duration not in panic.PANIC_DURATIONS:
            return Response({"duration": "Panic sessions are 15 or 30 minutes."}, status=400)

        note = request.data.get("note") or ""
        if not isinstance(note, str):
            return Response({"note": "The note should be a short line of text."}, status=400)
        note = note.strip()
        if len(note) > 200:
            return Response({"note": "Keep the note short — 200 characters is plenty."}, status=400)

        raw_start = request.data.get("start_time")
        start = parse_datetime(raw_start) if isinstance(raw_start, str) else None
        if start is None or timezone.is_naive(start):
            return Response(
                {"start_time": "Send the start time as an ISO datetime with a timezone offset."},
                status=400,
            )

        now = timezone.now()
        window_start, window_end = panic.booking_window(now)
        if not panic.is_aligned(start):
            return Response({"start_time": "Panic sessions start on 15-minute marks."}, status=400)
        if start < now + panic.PANIC_MIN_LEAD:
            return Response({"start_time": "Pick a time at least 30 minutes from now."}, status=400)
        if start > window_end:
            return Response({"start_time": "Pick a time within the next 48 hours."}, status=400)

        working_tz = panic.working_timezone_for(coach)
        display_tz = panic.display_timezone_for(request.user, working_tz)
        if not panic.is_within_bookable_hours(start, duration, working_tz):
            return Response(
                {
                    "start_time": (
                        f"Panic sessions are bookable {panic.PANIC_HOURS_TEXT} "
                        "in your coach's working hours."
                    )
                },
                status=400,
            )

        minutes_by_day = panic.panic_minutes_by_client_day(request.user, working_tz, display_tz)
        day = start.astimezone(display_tz).date()
        remaining = panic.remaining_minutes_for_day(minutes_by_day, day)
        if duration > remaining:
            day_word = "today" if day == now.astimezone(display_tz).date() else "that day"
            return Response(
                {
                    "detail": (
                        f"You've used your {panic.PANIC_DAILY_CAP_MINUTES} panic minutes for {day_word} "
                        f"— that's exactly what they're there for. {panic.cap_reset_text(display_tz, now)}"
                    )
                },
                status=409,
            )

        end = start + timedelta(minutes=duration)
        busy = panic.coach_busy_intervals(coach, window_start, window_end, working_tz)
        if panic.overlaps_any(start, end, busy):
            open_starts = panic.available_starts(
                coach, request.user, duration, now, busy=busy, minutes_by_day=minutes_by_day
            )
            suggestions = [
                alternative.astimezone(display_tz).isoformat()
                for alternative in panic.nearest_alternatives(start, open_starts)
            ]
            return Response(
                {
                    "detail": "Your coach is already booked then — here are the closest open times.",
                    "suggestions": suggestions,
                },
                status=409,
            )

        category, _ = EventCategory.objects.get_or_create(
            client=request.user,
            name=panic.PANIC_CATEGORY_NAME,
            defaults={"color": panic.PANIC_CATEGORY_COLOR},
        )
        local_start = start.astimezone(working_tz)
        local_end = end.astimezone(working_tz)
        event = Event(
            client=request.user,
            title=panic.PANIC_EVENT_TITLE,
            event_date=local_start.date(),
            start_time=local_start.time(),
            end_time=local_end.time(),
            description=note,
            category=category,
            is_panic=True,
        )
        event.save()

        # FAILURE RULE (same as EventViewSet): a Zoom problem never fails the booking.
        try:
            coach_profile = getattr(coach, "profile", None)
            host_email = coach_profile.zoom_user_email if coach_profile else None
            if not host_email:
                raise zoom.ZoomNotConfigured("No Zoom host email configured for this client's coach.")
            meeting = zoom.create_meeting(host_email, event)
            event.zoom_meeting_id = meeting["id"]
            event.meeting_link = meeting["join_url"]
            event.save()
            zoom_status = "ok"
        except Exception:
            logger.exception("Failed to create Zoom meeting for panic session %s", event.pk)
            zoom_status = "failed"

        # Emails and the ntfy ping are fail-soft in the notifications layer.
        send_panic_booked_client_email(
            request.user, coach, panic.format_when(start, display_tz), duration, event.meeting_link
        )
        send_panic_booked_coach_email(
            coach, request.user, panic.format_when(start, working_tz), duration, note
        )
        notify_panic_booked(event.client_name, panic.format_when(start, working_tz))

        row = _serialize_panic_session(event, working_tz, display_tz, now)
        row["zoom_status"] = zoom_status
        row["timezone"] = str(display_tz)
        return Response(row, status=201)


class PanicSessionDetailView(APIView):
    """Cancel (DELETE) one of the client's own upcoming panic sessions."""

    permission_classes = [permissions.IsAuthenticated, ClientOnlyPermission]

    @extend_schema(responses=None)
    def delete(self, request, pk):
        event = Event.objects.filter(pk=pk, client=request.user, is_panic=True).first()
        if event is None:
            return Response({"detail": "We couldn't find that panic session."}, status=404)

        coach = request.user.profile.assigned_coach
        working_tz = panic.working_timezone_for(coach)
        start = datetime.combine(event.event_date, event.start_time, tzinfo=working_tz)
        if start <= timezone.now():
            return Response(
                {"detail": "This session has already started — only upcoming panic sessions can be cancelled."},
                status=400,
            )

        meeting_id = event.zoom_meeting_id
        when_text = panic.format_when(start, working_tz)
        event.delete()
        if meeting_id is not None:
            try:
                zoom.delete_meeting(meeting_id)
            except zoom.ZoomError as exc:
                if exc.status_code != 404:  # a meeting already gone in Zoom is fine
                    logger.exception("Failed to delete Zoom meeting %s", meeting_id)
            except Exception:
                logger.exception("Failed to delete Zoom meeting %s", meeting_id)
        if coach is not None:
            send_panic_cancelled_coach_email(coach, request.user, when_text)
        return Response(status=204)


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
