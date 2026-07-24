from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminAnalyticsView,
    AdminManagedUserViewSet,
    ClientAssignmentViewSet,
    EventCategoryViewSet,
    EventViewSet,
    PanicAvailabilityView,
    PanicSessionDetailView,
    PanicSessionView,
    TaskViewSet,
    UserViewSet,
)

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("client-assignments", ClientAssignmentViewSet, basename="client-assignment")
router.register("admin/users", AdminManagedUserViewSet, basename="admin-user")
router.register("categories", EventCategoryViewSet, basename="category")
router.register("events", EventViewSet, basename="event")
router.register("tasks", TaskViewSet, basename="task")

urlpatterns = [
    path("admin/analytics/", AdminAnalyticsView.as_view(), name="admin-analytics"),
    path("panic-sessions/", PanicSessionView.as_view(), name="panic-session-list"),
    path("panic-sessions/<int:pk>/", PanicSessionDetailView.as_view(), name="panic-session-detail"),
    path("panic-availability/", PanicAvailabilityView.as_view(), name="panic-availability"),
    *router.urls,
]
