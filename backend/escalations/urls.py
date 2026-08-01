from django.urls import path

from .views import (
    EscalationDetailView,
    EscalationIngestView,
    EscalationListView,
    EscalationReopenView,
    EscalationTransitionView,
    ResolutionMethodListView,
)

urlpatterns = [
    path("ingest/", EscalationIngestView.as_view(), name="escalation-ingest"),
    path("methods/", ResolutionMethodListView.as_view(), name="escalation-methods"),
    path("", EscalationListView.as_view(), name="escalation-list"),
    path("<int:pk>/", EscalationDetailView.as_view(), name="escalation-detail"),
    path("<int:pk>/transition/", EscalationTransitionView.as_view(), name="escalation-transition"),
    path("<int:pk>/reopen/", EscalationReopenView.as_view(), name="escalation-reopen"),
]
