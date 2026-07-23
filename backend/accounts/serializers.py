from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from . import storage
from .models import ClientOnboarding, UserProfile, get_user_role


def validate_photo_upload(value):
    """FAIL-SOFT RULE: without R2 env, photo uploads are rejected with a clear
    message instead of silently landing in the local fallback storage."""
    if value and not storage.is_configured():
        raise serializers.ValidationError("Photo storage is not configured yet.")
    return value


class CoachCardSerializer(serializers.ModelSerializer):
    """Public card a coach shows to their assigned clients."""

    name = serializers.SerializerMethodField()
    photo_url = serializers.ImageField(source="profile.photo", read_only=True, use_url=True)
    bio = serializers.CharField(source="profile.bio", read_only=True)
    contact_email = serializers.EmailField(source="profile.contact_email", read_only=True)
    contact_phone = serializers.CharField(source="profile.contact_phone", read_only=True)

    class Meta:
        model = User
        fields = ["id", "name", "photo_url", "bio", "contact_email", "contact_phone"]

    def get_name(self, obj) -> str:
        return obj.get_full_name() or obj.username


class UserProfileSerializer(serializers.ModelSerializer):
    assigned_coach_id = serializers.IntegerField(source="assigned_coach.id", read_only=True)
    assigned_coach_name = serializers.SerializerMethodField()
    photo_url = serializers.ImageField(source="photo", read_only=True, use_url=True)

    class Meta:
        model = UserProfile
        fields = [
            "phone_number",
            "bio",
            "contact_email",
            "contact_phone",
            "photo_url",
            "assigned_coach_id",
            "assigned_coach_name",
        ]

    def get_assigned_coach_name(self, obj) -> str | None:
        if not obj.assigned_coach:
            return None
        return obj.assigned_coach.get_full_name() or obj.assigned_coach.username


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    """Self-service account settings: presentation/contact fields only."""

    photo = serializers.ImageField(required=False, allow_null=True, validators=[validate_photo_upload])

    class Meta:
        model = UserProfile
        fields = ["bio", "contact_email", "contact_phone", "photo"]


class CurrentUserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    profile = UserProfileSerializer(read_only=True)
    my_coach = serializers.SerializerMethodField()
    onboarding_complete = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
            "profile",
            "my_coach",
            "onboarding_complete",
        ]

    def get_role(self, obj) -> str | None:
        return get_user_role(obj)

    def get_onboarding_complete(self, obj) -> bool:
        onboarding = getattr(obj, "client_onboarding", None)
        return bool(onboarding and onboarding.completed_at)

    def get_my_coach(self, obj) -> dict | None:
        profile = getattr(obj, "profile", None)
        coach = profile.assigned_coach if profile else None
        if not coach:
            return None
        return CoachCardSerializer(coach, context=self.context).data


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(min_length=8, max_length=128)

    def validate_new_password_for_user(self, user):
        """Run Django's password validators with the resolved user as context."""
        try:
            validate_password(self.validated_data["new_password"], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": exc.messages})


class OnboardingSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientOnboarding
        fields = [
            "timezone",
            "morning_window",
            "evening_window",
            "contact_method",
            "contact_number",
            "help_topics",
            "completed_at",
        ]
        read_only_fields = ["completed_at"]

    def validate_timezone(self, value):
        if value not in ClientOnboarding.available_timezones():
            raise serializers.ValidationError("Choose a valid timezone.")
        return value


class LoginSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = get_user_role(user)
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = CurrentUserSerializer(self.user, context=self.context).data
        return data
