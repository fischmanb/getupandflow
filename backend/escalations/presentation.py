"""Small presentation helpers shared by the delivery layer and the API
serializers, so the phone UI and the push notification speak the same plain
clinical language.
"""

from .loader import load_triggers


def trigger_label(trigger_id):
    """Plain-language label for a trigger id, from triggers.yaml evidence text.
    Falls back to the id itself if the trigger is unknown to the spec."""
    try:
        trigger = load_triggers().by_id.get(trigger_id)
    except Exception:
        trigger = None
    if trigger and trigger.evidence:
        return trigger.evidence
    return trigger_id


def client_display_name(escalation):
    """Full identifier for the flagged client: the linked user's name/username,
    else the grader's free-text client_ref."""
    user = escalation.client
    if user is not None:
        return user.get_full_name() or user.username or (escalation.client_ref or "Unknown client")
    return escalation.client_ref or "Unknown client"


def client_initials(escalation):
    """Shoulder-surfing-safe initials only (max two letters)."""
    name = client_display_name(escalation).strip()
    parts = [p for p in name.replace("_", " ").split() if p]
    if not parts:
        return "??"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()
