"""Which applicants can be served today, and which go to the waitlist.

A zone is serviceable when its CURRENT UTC offset matches the offset of one of
the configured service timezones. Offset comparison (not name matching) means
every equivalent zone qualifies and DST transitions are handled by the tz
database rather than by us.
"""
from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings


def service_timezones():
    configured = getattr(settings, "GUAF_SERVICE_TIMEZONES", None) or []
    return [name for name in configured if name]


def _offset(name, at):
    try:
        return ZoneInfo(name).utcoffset(at)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def is_serviceable(tz_name, at=None):
    """True when tz_name is coverable by a service timezone right now.

    An unknown or empty zone is NOT serviceable: we route it to the waitlist
    rather than sell coverage we cannot verify.
    """
    if not tz_name:
        return False
    at = at or datetime.now(dt_timezone.utc)
    applicant = _offset(tz_name, at)
    if applicant is None:
        return False
    return any(_offset(name, at) == applicant for name in service_timezones())
