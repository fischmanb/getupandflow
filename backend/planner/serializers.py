from django.contrib.auth.models import Group, User
from django.utils import timezone
from rest_framework import serializers

from accounts.constants import ROLE_CLIENT, ROLE_COACH
from accounts.models import UserProfile, get_user_role

from .models import Event, EventCategory, Task
from .permissions import RBACScope


class UserSummarySerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    assigned_coach_id = serializers.IntegerField(source="profile.assigned_coach_id", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "role", "assigned_coach_id"]

    def get_role(self, obj) -> str | None:
        return get_user_role(obj)


class ClientAssignmentSerializer(serializers.ModelSerializer):
    user = UserSummarySerializer(read_only=True)

    class Meta:
        model = UserProfile
        fields = ["id", "user", "assigned_coach", "phone_number", "created_at", "updated_at"]


class EventCategorySerializer(serializers.ModelSerializer):
    # Writable on create so coaches/admins can specify the client.
    client_id = serializers.IntegerField(required=False)
    client = UserSummarySerializer(read_only=True)

    class Meta:
        model = EventCategory
        fields = ["id", "name", "color", "client", "client_id", "created_at", "updated_at"]
        # client_id is read-only on responses by virtue of being derived from the model field,
        # but we want it to round-trip on writes too. Mark fields nothing extra.

    def validate_client_id(self, value):
        request = self.context["request"]
        try:
            client = User.objects.get(pk=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("Client not found.")
        if not RBACScope.can_access_client(request.user, client):
            raise serializers.ValidationError("You do not have access to this client.")
        return value

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["client_id"] = instance.client_id
        return data

    def create(self, validated_data):
        client_id = validated_data.pop("client_id", None)
        if client_id is not None:
            validated_data["client_id"] = client_id
        return super().create(validated_data)


class ClientScopedValidationMixin:
    def validate_client(self, client):
        request = self.context["request"]
        if not RBACScope.can_access_client(request.user, client):
            raise serializers.ValidationError({"client_id": "You do not have access to this client."})
        if not client.profile.assigned_coach_id:
            raise serializers.ValidationError({"client_id": "Each client must have exactly one coach assigned."})
        return client


class EventSerializer(ClientScopedValidationMixin, serializers.ModelSerializer):
    client_id = serializers.PrimaryKeyRelatedField(
        source="client",
        queryset=User.objects.all(),
        write_only=True,
    )
    client = UserSummarySerializer(read_only=True)
    category_detail = EventCategorySerializer(source="category", read_only=True)

    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "event_date",
            "start_time",
            "end_time",
            "location",
            "meeting_link",
            "description",
            "category",
            "category_detail",
            "recurrence_type",
            "recurrence_until",
            "client",
            "client_id",
            "client_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["client_name", "created_at", "updated_at"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        client = attrs.get("client") or getattr(self.instance, "client", None)
        start_time = attrs.get("start_time") or getattr(self.instance, "start_time", None)
        end_time = attrs.get("end_time") or getattr(self.instance, "end_time", None)

        if client:
            self.validate_client(client)
        category = attrs.get("category") or getattr(self.instance, "category", None)
        recurrence_type = attrs.get("recurrence_type") or getattr(self.instance, "recurrence_type", Event.RecurrenceChoices.NONE)
        recurrence_until = attrs.get("recurrence_until") if "recurrence_until" in attrs else getattr(self.instance, "recurrence_until", None)
        if client and category and category.client_id != client.id:
            raise serializers.ValidationError({"category": "Selected category must belong to the chosen client."})
        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError({"end_time": "End time must be after start time."})
        if recurrence_type == Event.RecurrenceChoices.NONE:
            attrs["recurrence_until"] = None
        elif not recurrence_until:
            raise serializers.ValidationError({"recurrence_until": "Recurring events must include an end date."})
        elif recurrence_until < attrs.get("event_date", getattr(self.instance, "event_date", None)):
            raise serializers.ValidationError({"recurrence_until": "Recurring event end date must be on or after the start date."})
        return attrs


class TaskSerializer(ClientScopedValidationMixin, serializers.ModelSerializer):
    client_id = serializers.PrimaryKeyRelatedField(
        source="client",
        queryset=User.objects.all(),
        write_only=True,
    )
    client = UserSummarySerializer(read_only=True)

    class Meta:
        model = Task
        fields = [
            "id",
            "title",
            "deadline",
            "description",
            "completed_at",
            "priority",
            "sort_order",
            "client",
            "client_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        client = attrs.get("client") or getattr(self.instance, "client", None)
        if client:
            self.validate_client(client)
        return attrs


class AnalyticsSummarySerializer(serializers.Serializer):
    task_completion = serializers.ListField()
    events_per_day = serializers.ListField()
    events_per_month = serializers.ListField()


class AdminManagedUserCSVImportSerializer(serializers.Serializer):
    file = serializers.FileField()


class AdminManagedUserSerializer(serializers.ModelSerializer):
    role = serializers.CharField(write_only=True)
    assigned_coach_id = serializers.PrimaryKeyRelatedField(
        source="profile.assigned_coach",
        queryset=User.objects.filter(groups__name=ROLE_COACH).distinct(),
        allow_null=True,
        required=False,
    )
    phone_number = serializers.CharField(source="profile.phone_number", allow_blank=True, required=False)
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
            "phone_number",
            "assigned_coach_id",
            "password",
        ]
        read_only_fields = ["id"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["role"] = get_user_role(instance)
        return data

    def validate(self, attrs):
        attrs = super().validate(attrs)
        role = attrs.get("role") or (get_user_role(self.instance) if self.instance else None)
        if role not in {ROLE_COACH, ROLE_CLIENT}:
            raise serializers.ValidationError({"role": "Role must be Coach or Client."})
        profile_data = attrs.get("profile", {})
        assigned_coach = profile_data.get(
            "assigned_coach",
            self.instance.profile.assigned_coach if self.instance else None,
        )

        if role == ROLE_CLIENT and not assigned_coach:
            raise serializers.ValidationError({"assigned_coach_id": "Client users must have an assigned coach."})
        if role == ROLE_COACH and assigned_coach:
            raise serializers.ValidationError({"assigned_coach_id": "Coach users cannot have an assigned coach."})
        return attrs

    def create(self, validated_data):
        role = validated_data.pop("role")
        profile_data = validated_data.pop("profile", {})
        password = validated_data.pop("password")

        user = User(**validated_data)
        user.set_password(password)
        user.save()

        role_group = Group.objects.get(name=role)
        user.groups.set([role_group])

        profile = user.profile
        profile.phone_number = profile_data.get("phone_number", "")
        profile.assigned_coach = profile_data.get("assigned_coach")
        profile.save()

        return user

    def update(self, instance, validated_data):
        role = validated_data.pop("role", get_user_role(instance))
        profile_data = validated_data.pop("profile", {})
        password = validated_data.pop("password", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()

        role_group = Group.objects.get(name=role)
        instance.groups.set([role_group])

        profile = instance.profile
        if "phone_number" in profile_data:
            profile.phone_number = profile_data["phone_number"]
        if "assigned_coach" in profile_data or role == ROLE_COACH:
            profile.assigned_coach = None if role == ROLE_COACH else profile_data.get("assigned_coach")
        profile.save()

        return instance
