import logging

from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle

from .models import Lead
from .notify import send_signup_notifications
from .serializers import LeadSerializer


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
