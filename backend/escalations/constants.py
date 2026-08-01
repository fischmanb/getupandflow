"""Escalation lifecycle + delivery constants.

SLA hours, clocks, tiers, confidence thresholds and the business-hours timezone
are NOT here — those are read exclusively from triggers.yaml via
``escalations.loader`` (the single source of truth). This module holds the
things the YAML does not speak to: the queue lifecycle state machine and the
delivery env-var contract (topic/secret/recipient), each with a documented
default where a default is safe.
"""

import os

# ── Lifecycle states ────────────────────────────────────────────────────────
# open -> acknowledged -> in_review -> {escalated_to_clinical | resolved
#                                       | false_positive}
STATUS_OPEN = "open"
STATUS_ACKNOWLEDGED = "acknowledged"
STATUS_IN_REVIEW = "in_review"
STATUS_ESCALATED_TO_CLINICAL = "escalated_to_clinical"
STATUS_RESOLVED = "resolved"
STATUS_FALSE_POSITIVE = "false_positive"

STATUS_CHOICES = [
    (STATUS_OPEN, "Open"),
    (STATUS_ACKNOWLEDGED, "Acknowledged"),
    (STATUS_IN_REVIEW, "In review"),
    (STATUS_ESCALATED_TO_CLINICAL, "Escalated to clinical"),
    (STATUS_RESOLVED, "Resolved"),
    (STATUS_FALSE_POSITIVE, "False positive"),
]

# Terminal states — no transitions out. false_positive records are RETAINED
# (never deleted), same as resolved/escalated.
TERMINAL_STATUSES = frozenset({
    STATUS_ESCALATED_TO_CLINICAL,
    STATUS_RESOLVED,
    STATUS_FALSE_POSITIVE,
})

# The lifecycle graph: state -> set of states it may transition to. This is the
# ONLY authority on valid transitions; the API rejects anything not listed here
# (400 with the allowed next states).
ALLOWED_TRANSITIONS = {
    STATUS_OPEN: frozenset({STATUS_ACKNOWLEDGED}),
    STATUS_ACKNOWLEDGED: frozenset({STATUS_IN_REVIEW}),
    STATUS_IN_REVIEW: frozenset({
        STATUS_ESCALATED_TO_CLINICAL,
        STATUS_RESOLVED,
        STATUS_FALSE_POSITIVE,
    }),
    STATUS_ESCALATED_TO_CLINICAL: frozenset(),
    STATUS_RESOLVED: frozenset(),
    STATUS_FALSE_POSITIVE: frozenset(),
}

# Status-filter buckets the queue exposes (matches the phone UI's three tabs).
STATUS_FILTER_GROUPS = {
    "open": [STATUS_OPEN, STATUS_ACKNOWLEDGED],
    "in_review": [STATUS_IN_REVIEW],
    "closed": [
        STATUS_ESCALATED_TO_CLINICAL,
        STATUS_RESOLVED,
        STATUS_FALSE_POSITIVE,
    ],
}


def allowed_next_states(status):
    """Sorted list of states `status` may transition to (for 400 payloads)."""
    return sorted(ALLOWED_TRANSITIONS.get(status, frozenset()))


# ── Delivery contract (env-driven; documented defaults) ─────────────────────
# HMAC shared secret for the ingest endpoint. No default: absent secret must
# fail closed (every ingest rejected) rather than silently trust unsigned bodies.
INGEST_SECRET_ENV = "GUAF_ESCALATION_INGEST_SECRET"
INGEST_SIGNATURE_HEADER = "X-GUAF-Signature"

# ntfy topic for new-escalation push. Default is the GUAF clinical queue topic —
# deliberately NOT the aegis-brian-fischman personal topic.
NTFY_TOPIC_ENV = "GUAF_ESCALATION_NTFY_TOPIC"
DEFAULT_NTFY_TOPIC = "guaf-esc-ddf1fe5ab333"
NTFY_BASE_URL = "https://ntfy.sh"

# Clinical lead recipient for Tier-1 email (Bruce Parsons, MD). No default: an
# unset address disables T1 email (logged loudly) rather than mailing a guess.
CLINICAL_LEAD_EMAIL_ENV = "GUAF_CLINICAL_LEAD_EMAIL"


def get_ingest_secret():
    return os.getenv(INGEST_SECRET_ENV, "")


def get_ntfy_topic_url():
    topic = os.getenv(NTFY_TOPIC_ENV, DEFAULT_NTFY_TOPIC).strip() or DEFAULT_NTFY_TOPIC
    return f"{NTFY_BASE_URL}/{topic}"


def get_clinical_lead_email():
    return os.getenv(CLINICAL_LEAD_EMAIL_ENV, "").strip()
