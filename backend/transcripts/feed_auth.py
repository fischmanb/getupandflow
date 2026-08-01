"""HMAC gate for the outbound transcript feed.

sorel signs the RAW query string with the shared machine secret
(GUAF_ESCALATION_INGEST_SECRET — the same one the escalations ingest uses) and
sends the hex digest in X-GUAF-Signature. Constant-time; fail closed on an
unset secret or absent header.
"""

import hashlib
import hmac

from .constants import get_feed_secret


def feed_signature_valid(query_string, provided_signature):
    """True iff `provided_signature` == HMAC-SHA256(secret, query_string).

    `query_string` is the raw request query string (no leading '?'). Tolerates
    an optional ``sha256=`` prefix on the header.
    """
    secret = get_feed_secret()
    if not secret or not provided_signature:
        return False
    if isinstance(query_string, str):
        query_string = query_string.encode("utf-8")
    provided = provided_signature.strip()
    if provided.lower().startswith("sha256="):
        provided = provided[len("sha256="):]
    expected = hmac.new(secret.encode("utf-8"), query_string, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)
