"""SLA deadline computation — hours and clock read ENTIRELY from triggers.yaml.

Ported behaviour-for-behaviour from the ratified reference
`aegis2/guaf/sla.py`. Two clocks (policy.slas[tier].clock), no hour constant of
our own:

  - calendar (tier 1): deadline = received_at + N hours, wall-clock, any day.
    The most severe tier does not pause for weekends (SLA ruling 5cb4e5c8).

  - business_hours (tiers 2, 3): the clock runs only on business days
    (policy.business_hours: "Mon-Fri, <tz>; weekends excluded"). The YAML
    defines NO intra-day working window, so a business day contributes its full
    24 hours and weekends contribute zero. The creation day's remaining sliver
    is NOT credited: accrual begins at the start of the next business day, so a
    "24h business" SLA is one full business day of turnaround measured from the
    next business day. This is what makes a Friday-evening escalation due
    Tuesday (Fri -> next business day is Mon 00:00 -> +24h = Tue 00:00) — the
    weekend is skipped and the intake day is not counted. (A finer 9-5 window is
    intentionally NOT modelled: the YAML declares none, and inventing one would
    be a magic number the brief forbids.)

The timezone is whatever the YAML's business_hours definition names
(policy.business_hours_tz), never hardcoded here.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .loader import SLA, TriggerSpec, load_triggers

_SAT, _SUN = 5, 6  # datetime.weekday(): Mon=0 .. Sun=6


def _is_business_day(d: datetime) -> bool:
    return d.weekday() not in (_SAT, _SUN)


def business_hours_deadline(received_at: datetime, hours: int, tz: str) -> datetime:
    """Deadline `hours` business-hours after `received_at`, in zone `tz`.

    Accrual begins at the start of the first business day strictly after the
    intake day; each business day supplies 24 hours; weekend days supply none.
    Returned in `tz`.
    """
    zone = ZoneInfo(tz)
    local = received_at.astimezone(zone)
    # Start of the day after intake (the intake day's sliver is not credited).
    cursor = local.replace(hour=0, minute=0, second=0, microsecond=0) \
        + timedelta(days=1)
    remaining = hours
    while True:
        while not _is_business_day(cursor):
            cursor += timedelta(days=1)
        # A full business day (00:00 -> next 00:00) supplies 24 hours.
        if remaining <= 24:
            return cursor + timedelta(hours=remaining)
        remaining -= 24
        cursor += timedelta(days=1)


def sla_deadline(received_at: datetime, sla: SLA, tz: str) -> datetime:
    """Deadline for one SLA off its own clock. `received_at` must be timezone
    aware (the server's receipt time)."""
    if received_at.tzinfo is None:
        raise ValueError("sla_deadline needs a timezone-aware received_at")
    if sla.clock == "calendar":
        return received_at + timedelta(hours=sla.hours)
    if sla.clock == "business_hours":
        return business_hours_deadline(received_at, sla.hours, tz)
    raise ValueError(f"unknown SLA clock {sla.clock!r}")


def compute_sla_deadline(received_at: datetime, tier: int,
                         spec: TriggerSpec | None = None) -> datetime:
    """Server-authoritative SLA deadline for a `tier` escalation received at
    `received_at`. The single place ingest computes the deadline: hours, clock,
    and timezone all come from triggers.yaml via the spec — server math wins.
    """
    spec = spec or load_triggers()
    return sla_deadline(received_at, spec.sla_for_tier(tier),
                        spec.policy.business_hours_tz)
