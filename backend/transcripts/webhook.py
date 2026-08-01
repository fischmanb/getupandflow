"""Zoom webhook authenticity: the endpoint-URL validation challenge and the
per-event request-signature check.

Both use HMAC-SHA256 keyed on ZOOM_WEBHOOK_SECRET_TOKEN. Fail closed: with no
secret configured we can verify nothing, so every event is rejected and the
validation challenge is refused — never a silent trust of an unsigned callback.
"""

import hashlib
import hmac

from .constants import (
    ZOOM_SIGNATURE_MAX_SKEW_SECONDS,
    ZOOM_SIGNATURE_VERSION,
    get_webhook_secret,
)


def _hmac_hex(secret, message_bytes):
    return hmac.new(secret.encode("utf-8"), message_bytes, hashlib.sha256).hexdigest()


def validation_response(plain_token):
    """Answer Zoom's endpoint.url_validation challenge.

    Returns {"plainToken", "encryptedToken"} where encryptedToken is the hex
    HMAC of plainToken under the secret, or None if the secret is unset (the
    caller then refuses the challenge).
    """
    secret = get_webhook_secret()
    if not secret or not plain_token:
        return None
    return {
        "plainToken": plain_token,
        "encryptedToken": _hmac_hex(secret, plain_token.encode("utf-8")),
    }


def signature_valid(raw_body, timestamp, provided_signature, *, now_ts=None):
    """True iff `provided_signature` matches Zoom's v0 request signature.

    message = f"v0:{timestamp}:{raw_body}"
    signature = f"v0={hex_hmac(secret, message)}"

    Constant-time compare. Rejects a missing secret (fail closed), a missing
    header/timestamp, and a timestamp older than the replay window. `now_ts` is
    injectable for tests; production passes the wall clock.
    """
    secret = get_webhook_secret()
    if not secret or not provided_signature or not timestamp:
        return False

    try:
        ts_int = int(timestamp)
    except (TypeError, ValueError):
        return False
    if now_ts is not None and abs(now_ts - ts_int) > ZOOM_SIGNATURE_MAX_SKEW_SECONDS:
        return False

    if isinstance(raw_body, bytes):
        raw_body = raw_body.decode("utf-8", errors="replace")
    message = f"{ZOOM_SIGNATURE_VERSION}:{timestamp}:{raw_body}".encode("utf-8")
    expected = f"{ZOOM_SIGNATURE_VERSION}={_hmac_hex(secret, message)}"
    return hmac.compare_digest(expected, provided_signature.strip())
