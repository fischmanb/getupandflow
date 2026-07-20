from django.contrib import admin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "assigned_coach", "phone_number", "zoom_user_email", "created_at")
    search_fields = ("user__username", "user__email", "assigned_coach__username")
