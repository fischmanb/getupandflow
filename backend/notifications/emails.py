"""Transactional email senders.

Every sender is fail-soft: an email failure is logged and swallowed so it can
never break the request (or webhook) that triggered it.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger("notifications")

SUPPORT_EMAIL = "hello@getupandflow.co"


def send_templated_email(to_email, subject, template_base, context=None):
    """Render notifications/emails/<template_base>.{txt,html} and send. Fail-soft."""
    full_context = {
        "app_base_url": settings.APP_BASE_URL,
        "support_email": SUPPORT_EMAIL,
        **(context or {}),
    }
    try:
        text_body = render_to_string(f"notifications/emails/{template_base}.txt", full_context)
        html_body = render_to_string(f"notifications/emails/{template_base}.html", full_context)
        message = EmailMultiAlternatives(subject=subject, body=text_body, to=[to_email])
        message.attach_alternative(html_body, "text/html")
        message.send()
        return True
    except Exception:
        logger.exception("Failed to send %s email to %s", template_base, to_email)
        return False


def send_welcome_email(user, plan_name=""):
    """Post-payment welcome / expectation-set email."""
    return send_templated_email(
        user.email,
        "Welcome to Get Up and Flow — you're in",
        "welcome",
        {
            "first_name": user.first_name or "there",
            "plan_name": plan_name,
            "onboarding_url": f"{settings.APP_BASE_URL}/app/onboarding",
            "login_url": f"{settings.APP_BASE_URL}/login",
        },
    )


def send_coach_assigned_email(client, coach):
    coach_first_name = coach.first_name or coach.get_full_name() or coach.username
    return send_templated_email(
        client.email,
        f"Meet your coach, {coach_first_name}",
        "coach_assigned",
        {
            "first_name": client.first_name or "there",
            "coach_first_name": coach_first_name,
            "login_url": f"{settings.APP_BASE_URL}/login",
        },
    )


def send_password_reset_email(user, reset_url):
    return send_templated_email(
        user.email,
        "Reset your Get Up and Flow password",
        "password_reset",
        {
            "first_name": user.first_name or "there",
            "reset_url": reset_url,
        },
    )
