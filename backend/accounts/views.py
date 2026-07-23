from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from billing.permissions import ClientOnlyPermission
from notifications.emails import send_password_reset_email

from .models import ClientOnboarding
from .serializers import (
    CurrentUserSerializer,
    LoginSerializer,
    OnboardingSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    UserProfileUpdateSerializer,
)


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer


class RefreshView(TokenRefreshView):
    pass


class PasswordResetRequestView(APIView):
    """Send a password reset email. Always 200 -- no account enumeration."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"
    serializer_class = PasswordResetRequestSerializer

    @extend_schema(request=PasswordResetRequestSerializer, responses=None)
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        users = User.objects.filter(email__iexact=email, is_active=True)
        for user in users:
            if not user.has_usable_password():
                continue
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_url = f"{settings.APP_BASE_URL}/reset-password?uid={uid}&token={token}"
            send_password_reset_email(user, reset_url)
        return Response(
            {"detail": "If an account exists for this email, a reset link is on its way."}
        )


class PasswordResetConfirmView(APIView):
    """Set a new password given a valid uid + token from the reset email."""

    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = PasswordResetConfirmSerializer

    @extend_schema(request=PasswordResetConfirmSerializer, responses=None)
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        invalid = Response(
            {"detail": "This reset link is invalid or has expired. Please request a new one."},
            status=status.HTTP_400_BAD_REQUEST,
        )
        try:
            user_pk = force_str(urlsafe_base64_decode(data["uid"]))
            user = User.objects.get(pk=user_pk, is_active=True)
        except (ValueError, OverflowError, User.DoesNotExist):
            return invalid
        if not default_token_generator.check_token(user, data["token"]):
            return invalid

        serializer.validate_new_password_for_user(user)
        user.set_password(data["new_password"])
        user.save(update_fields=["password"])
        return Response({"detail": "Your password has been reset. You can now log in."})


class OnboardingView(APIView):
    """The client's own onboarding answers: GET returns them (or null), PUT upserts."""

    permission_classes = [IsAuthenticated, ClientOnlyPermission]
    serializer_class = OnboardingSerializer

    @extend_schema(responses=OnboardingSerializer)
    def get(self, request):
        onboarding = ClientOnboarding.objects.filter(user=request.user).first()
        if onboarding is None:
            return Response(None)
        return Response(OnboardingSerializer(onboarding).data)

    @extend_schema(request=OnboardingSerializer, responses=OnboardingSerializer)
    def put(self, request):
        onboarding = ClientOnboarding.objects.filter(user=request.user).first()
        serializer = OnboardingSerializer(onboarding, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return Response(serializer.data)


class MeView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CurrentUserSerializer

    @extend_schema(responses=CurrentUserSerializer)
    def get(self, request):
        return Response(CurrentUserSerializer(request.user, context={"request": request}).data)

    @extend_schema(request=UserProfileUpdateSerializer, responses=CurrentUserSerializer)
    def patch(self, request):
        serializer = UserProfileUpdateSerializer(request.user.profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(CurrentUserSerializer(request.user, context={"request": request}).data)
