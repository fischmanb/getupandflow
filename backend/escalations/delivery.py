"""Delivery on escalation create: ntfy push (all tiers) + Tier-1 clinical email.

Both transports fail LOUDLY, never silently: a transport error is logged at
error level with full context (and re-raised context via exc_info) but does not
undo the escalation that already committed. The escalation record is the source
of truth; delivery is best-effort notification on top of it. What we never do is
swallow a failure without a trace — an undelivered Tier-1 push must be visible
in the logs.
"""

import logging

import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from .constants import get_clinical_lead_email, get_ntfy_topic_url
from .presentation import client_initials, trigger_label

logger = logging.getLogger("escalations")

# ntfy priority: 5 = urgent (bypasses phone quiet hours). Tier 1 only.
_TIER1_NTFY_PRIORITY = "5"
_DEFAULT_NTFY_PRIORITY = "4"  # high


def _deadline_str(escalation):
    return timezone.localtime(escalation.sla_deadline_at).strftime("%a %b %-d, %-I:%M %p %Z")


def send_escalation_push(escalation):
    """POST the escalation to the ntfy topic. Returns True on delivery.

    Raises requests exceptions on transport failure — the caller logs loudly.
    Never sends to the personal aegis topic: the URL comes from
    GUAF_ESCALATION_NTFY_TOPIC (default the GUAF clinical queue topic).
    """
    url = get_ntfy_topic_url()
    label = trigger_label(escalation.trigger_id)
    initials = client_initials(escalation)
    is_tier1 = escalation.tier == 1
    title = f"Tier {escalation.tier} escalation" + (" — immediate" if is_tier1 else "")
    body = (
        f"{label}\n"
        f"Client {initials} · confidence {escalation.confidence:.0%}\n"
        f"Due {_deadline_str(escalation)}"
    )
    headers = {
        "Title": title,
        "Priority": _TIER1_NTFY_PRIORITY if is_tier1 else _DEFAULT_NTFY_PRIORITY,
        "Tags": "rotating_light" if is_tier1 else "warning",
    }
    response = requests.post(
        url, data=body.encode("utf-8"), headers=headers, timeout=5
    )
    response.raise_for_status()
    return True


def send_tier1_clinical_email(escalation):
    """Email the clinical lead about a Tier-1 escalation. Returns True on send,
    False if no recipient is configured (logged loudly). Raises on send failure.
    """
    to_email = get_clinical_lead_email()
    if not to_email:
        logger.error(
            "Tier-1 escalation %s: no GUAF_CLINICAL_LEAD_EMAIL configured — "
            "clinical lead NOT emailed",
            escalation.pk,
        )
        return False
    context = {
        "trigger_label": trigger_label(escalation.trigger_id),
        "client_initials": client_initials(escalation),
        "confidence_pct": f"{escalation.confidence:.0%}",
        "deadline": _deadline_str(escalation),
        "queue_url": f"{settings.APP_BASE_URL}/escalations",
    }
    subject = f"Tier 1 escalation — {context['trigger_label']}"
    text_body = render_to_string("escalations/emails/tier1_alert.txt", context)
    html_body = render_to_string("escalations/emails/tier1_alert.html", context)
    message = EmailMultiAlternatives(subject=subject, body=text_body, to=[to_email])
    message.attach_alternative(html_body, "text/html")
    message.send()
    return True


def deliver_escalation(escalation):
    """Fire all delivery for a freshly created escalation. Call on_commit so it
    runs after the row is durably persisted. Each transport is isolated: a push
    failure never blocks the Tier-1 email, and neither is ever swallowed.
    """
    try:
        send_escalation_push(escalation)
    except Exception:
        logger.error(
            "Escalation %s: ntfy push FAILED (tier %s, trigger %s)",
            escalation.pk, escalation.tier, escalation.trigger_id,
            exc_info=True,
        )

    if escalation.tier == 1:
        try:
            send_tier1_clinical_email(escalation)
        except Exception:
            logger.error(
                "Tier-1 escalation %s: clinical-lead email FAILED",
                escalation.pk, exc_info=True,
            )
