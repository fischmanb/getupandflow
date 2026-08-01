from django.urls import path

from .views import (
    EscalationDetailView,
    EscalationIngestView,
    EscalationListView,
    EscalationTransitionView,
)

urlpatterns = [
    path("ingest/", EscalationIngestView.as_view(), name="escalation-ingest"),
    path("", EscalationListView.as_view(), name="escalation-list"),
    path("<int:pk>/", EscalationDetailView.as_view(), name="escalation-detail"),
    path("<int:pk>/transition/", EscalationTransitionView.as_view(), name="escalation-transition"),
]
