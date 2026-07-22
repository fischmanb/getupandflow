from rest_framework import permissions

from planner.permissions import RBACScope


class ClientOnlyPermission(permissions.BasePermission):
    """Allow only authenticated users whose role is Client."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and RBACScope.is_client(request.user)
        )
