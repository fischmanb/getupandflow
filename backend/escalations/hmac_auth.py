"""HMAC-SHA256 verification for the grader ingest endpoint.

The grading engine signs the RAW request body with the shared secret
(GUAF_ESCALATION_INGEST_SECRET) and sends the hex digest in the
X-GUAF-Signature header. Verification is constant-time. Fail closed: an unset
secret means we cannot verify anyone, so every ingest is rejected — never a
silent trust of unsigned bodies.
"""

import hashlib
import hmac

from .constants import get_ingest_secret


def _expected_signature(secret, raw_body):
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def signature_valid(raw_body, provided_signature):
    """True iff `provided_signature` matches HMAC-SHA256(secret, raw_body).

    Returns False when the secret is unset (fail closed) or the header is
    absent/empty. Tolerates an optional ``sha256=`` prefix on the header.
    """
    secret = get_ingest_secret()
    if not secret:
        return False
    if not provided_signature:
        return False
    provided = provided_signature.strip()
    if provided.lower().startswith("sha256="):
        provided = provided[len("sha256="):]
    expected = _expected_signature(secret, raw_body)
    return hmac.compare_digest(expected, provided)
