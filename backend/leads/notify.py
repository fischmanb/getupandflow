"""Signup notifications: ntfy push + email to founders on every new Lead.

Delivery is best-effort by design: the lead is already saved before this
runs, and no failure here may ever surface to the signer-upper. Two
independent channels; each wrapped; failures logged loudly.

Env:
  GUAF_SIGNUP_NTFY_TOPIC   -- ntfy topic URL (default: settings.NTFY_TOPIC_URL)
  GUAF_SIGNUP_NOTIFY_EMAILS -- comma-separated recipients; unset = email skipped
"""
import json
import logging
import os
import urllib.request

from django.conf import settings
from django.core.mail import EmailMessage

logger = logging.getLogger(__name__)

_NTFY_TIMEOUT_S = 6


def _ntfy_url():
    return os.getenv("GUAF_SIGNUP_NTFY_TOPIC", getattr(settings, "NTFY_TOPIC_URL", "")).strip()


def _recipients():
    raw = os.getenv("GUAF_SIGNUP_NOTIFY_EMAILS", "")
    return [a.strip() for a in raw.split(",") if a.strip()]


def _push_ntfy(lead):
    url = _ntfy_url()
    if not url:
        logger.error("Signup %s: no ntfy topic configured", lead.pk)
        return False
    # JSON publish endpoint: HTTP headers are latin-1 only, so any non-latin-1
    # character in a lead name (em dash, curly quote, most non-Western names)
    # would crash a Title header. The JSON body is UTF-8 end to end.
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    base = "%s://%s" % (parts.scheme, parts.netloc)
    topic = parts.path.strip("/")
    message = "%s <%s>\n%s / %s\nNotes: %s\nAdmin: https://api.getupandflow.co/admin/leads/lead/%s/change/" % (
        lead.full_name, lead.email, lead.get_plan_display(),
        lead.get_billing_period_display(), (lead.notes or "-")[:300], lead.pk,
    )
    payload = json.dumps({
        "topic": topic,
        "title": "NEW GUAF SIGNUP: %s" % lead.full_name,
        "message": message,
        "priority": 4,
        "tags": ["tada", "moneybag"],
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    token = os.getenv("GUAF_SIGNUP_NTFY_TOKEN", "").strip()
    if token:
        headers["Authorization"] = "Bearer %s" % token
    req = urllib.request.Request(base, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=_NTFY_TIMEOUT_S) as resp:
            ok = 200 <= resp.status < 300
    except Exception:
        logger.exception("Signup %s: ntfy push FAILED", lead.pk)
        return False
    if not ok:
        logger.error("Signup %s: ntfy push non-2xx", lead.pk)
    return ok


def _send_email(lead):
    to = _recipients()
    if not to:
        logger.warning("Signup %s: GUAF_SIGNUP_NOTIFY_EMAILS unset; email skipped", lead.pk)
        return False
    subject = "\U0001f7e2 NEW GUAF SIGNUP \u2014 %s (%s)" % (lead.full_name, lead.get_plan_display())
    body = (
        "New signup on getupandflow.co\n\n"
        "Name:    %s\nEmail:   %s\nPlan:    %s\nBilling: %s\nNotes:   %s\nWhen:    %s\n\n"
        "Lead in admin: https://api.getupandflow.co/admin/leads/lead/%s/change/\n"
    ) % (
        lead.full_name, lead.email, lead.get_plan_display(),
        lead.get_billing_period_display(), lead.notes or "-",
        lead.created_at.isoformat(), lead.pk,
    )
    lead_url = "https://api.getupandflow.co/admin/leads/lead/%s/change/" % lead.pk
    list_url = "https://api.getupandflow.co/admin/leads/lead/"
    html = """\
<div style="font-family:-apple-system,Segoe UI,Arial,sans-serif;max-width:560px;margin:0 auto;padding:24px">
  <div style="font-size:30px;font-weight:800;color:#065f46;line-height:1.25;margin-bottom:6px">
    \U0001f7e2 A new customer signed up for Get Up and Flow
  </div>
  <div style="font-size:16px;color:#334155;margin-bottom:20px">Review the lead and start onboarding.</div>
  <table style="border-collapse:collapse;font-size:15px;color:#0f172a;margin-bottom:24px">
    <tr><td style="padding:4px 14px 4px 0;color:#64748b">Name</td><td style="padding:4px 0;font-weight:700">%(name)s</td></tr>
    <tr><td style="padding:4px 14px 4px 0;color:#64748b">Email</td><td style="padding:4px 0">%(email)s</td></tr>
    <tr><td style="padding:4px 14px 4px 0;color:#64748b">Plan</td><td style="padding:4px 0">%(plan)s / %(billing)s</td></tr>
    <tr><td style="padding:4px 14px 4px 0;color:#64748b;vertical-align:top">Notes</td><td style="padding:4px 0">%(notes)s</td></tr>
  </table>
  <a href="%(lead_url)s" style="display:inline-block;background:#059669;color:#ffffff;font-size:19px;font-weight:800;padding:15px 30px;border-radius:10px;text-decoration:none">REVIEW LEAD IN ADMIN &rarr;</a>
  <div style="font-size:13px;color:#64748b;margin-top:16px">All leads: <a href="%(list_url)s" style="color:#2563eb">%(list_url)s</a></div>
</div>""" % {
        "name": lead.full_name, "email": lead.email,
        "plan": lead.get_plan_display(), "billing": lead.get_billing_period_display(),
        "notes": (lead.notes or "-"), "lead_url": lead_url, "list_url": list_url,
    }
    from django.core.mail import EmailMultiAlternatives
    msg = EmailMultiAlternatives(subject=subject, body=body, to=to)
    msg.attach_alternative(html, "text/html")
    msg.extra_headers = {"X-Priority": "1", "Importance": "high"}
    try:
        sent = msg.send(fail_silently=False)
    except Exception:
        logger.exception("Signup %s: notification email FAILED", lead.pk)
        return False
    if not sent:
        logger.error("Signup %s: notification email reported 0 sent", lead.pk)
    return bool(sent)


def send_signup_notifications(lead):
    """Fire both channels; never raise."""
    try:
        _push_ntfy(lead)
    except Exception:
        logger.exception("Signup %s: ntfy channel crashed", lead.pk)
    try:
        _send_email(lead)
    except Exception:
        logger.exception("Signup %s: email channel crashed", lead.pk)
