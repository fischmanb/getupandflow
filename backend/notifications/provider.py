"""Env-driven email provider selection.

Stdlib-only on purpose: settings.py imports this before Django app loading,
so it must not touch Django. The provider is chosen purely by environment:
EMAIL_PROVIDER=postmark|resend|console. Unset, unknown, or missing
credentials all fall back to the console backend (fail-soft) so a
misconfigured mail environment can never take requests down.
"""

CONSOLE_BACKEND = "django.core.mail.backends.console.EmailBackend"
POSTMARK_BACKEND = "anymail.backends.postmark.EmailBackend"
RESEND_BACKEND = "anymail.backends.resend.EmailBackend"


def select_email_backend(provider, postmark_server_token="", resend_api_key=""):
    """Return (backend_path, anymail_settings) for the configured provider."""
    provider = (provider or "").strip().lower()
    if provider == "postmark" and postmark_server_token:
        return POSTMARK_BACKEND, {"POSTMARK_SERVER_TOKEN": postmark_server_token}
    if provider == "resend" and resend_api_key:
        return RESEND_BACKEND, {"RESEND_API_KEY": resend_api_key}
    return CONSOLE_BACKEND, {}
