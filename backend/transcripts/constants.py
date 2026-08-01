"""Transcript pipeline constants.

Everything with a knob is named here (no magic numbers in the code paths):
webhook auth scheme, the deferred-retry delay, the feed page size, and the
shared-secret env contract. Delays/sizes are env-overridable with documented
defaults and a derivation note.
"""

import os

# ── Grading lifecycle ───────────────────────────────────────────────────────
# A transcript lands `pending`; the outbound grading engine (sorel) pulls it
# via the feed and later marks it graded/failed. Stored on the row so the feed
# can expose progress without a second system of record.
GRADING_PENDING = "pending"
GRADING_GRADED = "graded"
GRADING_FAILED = "failed"
GRADING_STATUS_CHOICES = [
    (GRADING_PENDING, "Pending"),
    (GRADING_GRADED, "Graded"),
    (GRADING_FAILED, "Failed"),
]

# ── Zoom webhook contract ───────────────────────────────────────────────────
# Secret token from the Zoom App Marketplace "Feature > Event Subscriptions"
# page. Used for BOTH the endpoint-URL validation challenge and per-event
# signature verification. No default: absent secret fails closed (every event
# rejected) rather than trusting unsigned callbacks.
ZOOM_WEBHOOK_SECRET_ENV = "ZOOM_WEBHOOK_SECRET_TOKEN"
# Zoom's request-signature scheme is versioned; "v0" is the current one.
# message = f"v0:{timestamp}:{raw_body}" ; signature = f"v0={hex_hmac}".
ZOOM_SIGNATURE_VERSION = "v0"
ZOOM_SIGNATURE_HEADER = "x-zm-signature"
ZOOM_SIGNATURE_TIMESTAMP_HEADER = "x-zm-request-timestamp"
# Reject events whose signed timestamp is older than this (replay guard). Zoom
# recommends 5 minutes; expressed in seconds.
ZOOM_SIGNATURE_MAX_SKEW_SECONDS = int(os.getenv("ZOOM_SIGNATURE_MAX_SKEW_SECONDS", str(5 * 60)))

# Zoom event names we act on. recording.completed carries the full recording
# set; the TRANSCRIPT VTT is sometimes generated later and arrives on its own
# recording.transcript_completed event — we handle both identically.
ZOOM_EVENT_URL_VALIDATION = "endpoint.url_validation"
ZOOM_EVENT_RECORDING_COMPLETED = "recording.completed"
ZOOM_EVENT_TRANSCRIPT_COMPLETED = "recording.transcript_completed"

# The recording_files[].file_type that is the transcript VTT.
ZOOM_TRANSCRIPT_FILE_TYPE = "TRANSCRIPT"

# ── Deferred poll-once retry ────────────────────────────────────────────────
# When the TRANSCRIPT file 404s (listed but not yet materialized), retry the
# download exactly ONCE after this delay via a one-shot daemon thread (no new
# daemon/queue). Default 90s: Zoom typically finishes transcript generation
# within a minute or two of the recording; one short wait covers the common lag
# without holding a request. Env-overridable for ops.
TRANSCRIPT_RETRY_DELAY_SECONDS = int(os.getenv("ZOOM_TRANSCRIPT_RETRY_DELAY_SECONDS", "90"))

# ── Feed for sorel (outbound pull) ──────────────────────────────────────────
# Feed requests are signed with the SAME shared machine secret as the
# escalations ingest (one secret per machine boundary): HMAC-SHA256 of the raw
# query string, hex, in X-GUAF-Signature. Reuse of the env name is deliberate.
FEED_SIGNATURE_HEADER = "X-GUAF-Signature"
FEED_SECRET_ENV = "GUAF_ESCALATION_INGEST_SECRET"
# Feed page size. Default 50: transcripts are low-volume (one per coaching
# session) but plain_text can be large, so keep pages modest. Env-overridable.
FEED_PAGE_SIZE = int(os.getenv("GUAF_TRANSCRIPT_FEED_PAGE_SIZE", "50"))
FEED_MAX_PAGE_SIZE = 200


def get_webhook_secret():
    return os.getenv(ZOOM_WEBHOOK_SECRET_ENV, "")


def get_feed_secret():
    return os.getenv(FEED_SECRET_ENV, "")
