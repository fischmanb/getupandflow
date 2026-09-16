import logging

from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle

from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Lead, WaitlistEntry
from .notify import send_signup_notifications, send_waitlist_notifications
from .serializers import LeadSerializer, WaitlistEntrySerializer
from .service_area import is_serviceable, service_timezones


class ServiceAreaView(APIView):
    """Tells the signup form whether a timezone can be served right now.

    The form calls this instead of embedding coverage rules in the client, so
    widening coverage is a server env change with no redeploy of the frontend.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        tz_name = request.query_params.get("timezone", "")
        return Response(
            {
                "timezone": tz_name,
                "serviceable": is_serviceable(tz_name),
                "service_timezones": service_timezones(),
            }
        )


class WaitlistCreateView(generics.CreateAPIView):
    queryset = WaitlistEntry.objects.all()
    serializer_class = WaitlistEntrySerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "leads"

    def perform_create(self, serializer):
        entry = serializer.save()
        try:
            send_waitlist_notifications(entry)
        except Exception:
            logging.getLogger(__name__).exception(
                "Waitlist entry %s saved but notifications crashed", entry.pk
            )


class LeadCreateView(generics.CreateAPIView):
    queryset = Lead.objects.all()
    serializer_class = LeadSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "leads"

    def perform_create(self, serializer):
        lead = serializer.save()
        # Notifications are strictly post-save and may never break signup:
        # notify.py never raises, and this guard makes it structural.
        try:
            send_signup_notifications(lead)
        except Exception:
            logging.getLogger(__name__).exception(
                "Lead %s saved but signup notifications crashed", lead.pk
            )
