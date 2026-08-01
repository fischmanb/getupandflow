"""Recording-consent gate.

A transcript is stored ONLY for a client whose profile carries recording
consent. Consent is modeled explicitly on UserProfile.recording_consent
(default True, derived from ToS acceptance for existing rows) so it can be
revoked. Missing profile → no basis for consent → treat as NOT consented.
"""


def client_has_recording_consent(client):
    if client is None:
        return False
    profile = getattr(client, "profile", None)
    if profile is None:
        return False
    return bool(profile.recording_consent)
