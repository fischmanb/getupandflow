from django.urls import path

from .views import LeadCreateView

urlpatterns = [
    path("", LeadCreateView.as_view(), name="lead-create"),
]
