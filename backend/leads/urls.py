from django.urls import path

from .views import LeadCreateView, ServiceAreaView, WaitlistCreateView

urlpatterns = [
    path("", LeadCreateView.as_view(), name="lead-create"),
    path("waitlist/", WaitlistCreateView.as_view(), name="waitlist-create"),
    path("service-area/", ServiceAreaView.as_view(), name="service-area"),
]
