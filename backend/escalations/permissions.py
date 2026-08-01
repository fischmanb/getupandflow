from rest_framework import permissions

from planner.permissions import RBACScope


class LeadershipPermission(permissions.BasePermission):
    """Queue access is leadership-only — the same admin gate the admin
    dashboard endpoints use (planner.AdminOnlyPermission → RBACScope.is_admin).
    Kept as its own class so the escalation surface has one obvious auth seam.
    """

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and RBACScope.is_admin(request.user)
        )
