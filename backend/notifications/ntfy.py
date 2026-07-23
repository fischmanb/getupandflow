"""Fail-soft push notifications via ntfy.sh."""

import logging

import requests
from django.conf import settings

logger = logging.getLogger("notifications")


def send_ntfy(message):
    """POST a message to the configured ntfy topic. Never raises."""
    url = settings.NTFY_TOPIC_URL
    if not url:
        return False
    try:
        response = requests.post(url, data=message.encode("utf-8"), timeout=5)
        response.raise_for_status()
        return True
    except Exception:
        logger.exception("Failed to send ntfy notification: %s", message)
        return False


def notify_new_paid_signup(email, plan_name):
    return send_ntfy(f"GUAF: new paid signup {email} {plan_name}")
