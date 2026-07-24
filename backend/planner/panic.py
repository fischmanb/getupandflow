"""Panic Button booking rules and availability.

Panic sessions are short ad-hoc calls a client books from their coach's
calendar to restart momentum. This module is the single home for the policy
and the arithmetic; the views in planner.views only orchestrate.

Timezone semantics (Brian, 2026-07-24, addendum 3):
- Bookable hours are evaluated in the coach's assigned ``working_timezone`` —
  never the server's timezone, never a "local" guess.
- Everything shown to the client (slots, day grouping, cap-reset language)
  renders in the client's stored onboarding timezone, falling back to the
  coach's working timezone, then UTC.
- Event rows store naive wall-clock date/times; a coach's calendar is kept in
  their working timezone, so stored values are interpreted there.
"""

import zoneinfo
from datetime import datetime, time, timedelta

from accounts.constants import DEFAULT_WORKING_TIMEZONE

from .models import Event
from .recurrence import expand_event_dates

# POLICY (Brian, 2026-07-24, .tasks/panic-booking.md + addenda 2-3): panic
# sessions are 15 or 30 minutes, at most 45 minutes per client per calendar
# day (the client's day), requested 30 minutes to 48 hours ahead on a 15-min
# grid, and bookable ONLY 8:00am-5:00pm Monday-Friday in the coach's
# working_timezone. This is the one place those numbers live.
PANIC_DURATIONS = (15, 30)
PANIC_DAILY_CAP_MINUTES = 45
PANIC_MIN_LEAD = timedelta(minutes=30)
PANIC_MAX_HORIZON = timedelta(hours=48)
PANIC_SLOT_MINUTES = 15
PANIC_BOOKABLE_START = time(8, 0)
PANIC_BOOKABLE_END = time(17, 0)
PANIC_BOOKABLE_WEEKDAYS = (0, 1, 2, 3, 4)  # Monday-Friday
PANIC_HOURS_TEXT = "8:00am-5:00pm, Monday to Friday"

PANIC_EVENT_TITLE = "Panic session"
PANIC_CATEGORY_NAME = "Panic Button"
PANIC_CATEGORY_COLOR = "rose"


def _safe_zone(name):
    try:
        return zoneinfo.ZoneInfo(name) if name else None
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return None


def working_timezone_for(coach):
    """The timezone the coach's bookable hours (and calendar) live in."""
    profile = getattr(coach, "profile", None)
    zone = _safe_zone(getattr(profile, "working_timezone", None))
    return zone or zoneinfo.ZoneInfo(DEFAULT_WORKING_TIMEZONE)


def display_timezone_for(client, working_tz):
    """Client's stored onboarding timezone, then coach working tz, then UTC."""
    onboarding = getattr(client, "client_onboarding", None)
    zone = _safe_zone(getattr(onboarding, "timezone", None))
    return zone or working_tz or zoneinfo.ZoneInfo("UTC")


def _ceil_to_grid(instant):
    floored = instant.replace(second=0, microsecond=0)
    floored -= timedelta(minutes=floored.minute % PANIC_SLOT_MINUTES)
    if floored < instant:
        floored += timedelta(minutes=PANIC_SLOT_MINUTES)
    return floored


def booking_window(now):
    """[earliest, latest] allowed start instants, earliest ceiled to the grid.

    Grid alignment is timezone-independent: every IANA offset is a whole
    multiple of 15 minutes, so a start aligned in UTC is aligned everywhere.
    """
    return _ceil_to_grid(now + PANIC_MIN_LEAD), now + PANIC_MAX_HORIZON


def is_aligned(start):
    return start.second == 0 and start.microsecond == 0 and start.minute % PANIC_SLOT_MINUTES == 0


def is_within_bookable_hours(start, duration_minutes, working_tz):
    """True when the whole session fits inside 8-5 Mon-Fri in the working tz."""
    local_start = start.astimezone(working_tz)
    local_end = local_start + timedelta(minutes=duration_minutes)
    return (
        local_start.weekday() in PANIC_BOOKABLE_WEEKDAYS
        and local_start.time() >= PANIC_BOOKABLE_START
        and local_end.date() == local_start.date()
        and local_end.time() <= PANIC_BOOKABLE_END
    )


def coach_busy_intervals(coach, window_start, window_end, working_tz, exclude_event_id=None):
    """Aware [start, end) intervals for every event on the coach's calendar.

    The coach's calendar is the union of their assigned clients' events,
    recurring occurrences expanded. Only intervals overlapping the window are
    returned — this one query is the whole MVP "availability" story.
    """
    range_start = window_start.astimezone(working_tz).date() - timedelta(days=1)
    range_end = window_end.astimezone(working_tz).date() + timedelta(days=1)
    events = Event.objects.filter(client__profile__assigned_coach=coach)
    if exclude_event_id is not None:
        events = events.exclude(pk=exclude_event_id)

    intervals = []
    for event in events:
        for day in expand_event_dates(
            event.event_date, event.recurrence_type, event.recurrence_until, range_start, range_end
        ):
            start = datetime.combine(day, event.start_time, tzinfo=working_tz)
            end = datetime.combine(day, event.end_time, tzinfo=working_tz)
            if end > window_start and start < window_end:
                intervals.append((start, end))
    return intervals


def overlaps_any(start, end, intervals):
    return any(busy_start < end and busy_end > start for busy_start, busy_end in intervals)


def panic_minutes_by_client_day(client, working_tz, display_tz, exclude_event_id=None):
    """Booked panic minutes per calendar day OF THE CLIENT (their timezone).

    The daily cap resets at the client's midnight, so sessions are bucketed by
    the client-timezone date of their start.
    """
    events = Event.objects.filter(client=client, is_panic=True)
    if exclude_event_id is not None:
        events = events.exclude(pk=exclude_event_id)

    totals = {}
    for event in events:
        start = datetime.combine(event.event_date, event.start_time, tzinfo=working_tz)
        end = datetime.combine(event.event_date, event.end_time, tzinfo=working_tz)
        day = start.astimezone(display_tz).date()
        totals[day] = totals.get(day, 0) + int((end - start).total_seconds() // 60)
    return totals


def remaining_minutes_for_day(minutes_by_day, day):
    return max(0, PANIC_DAILY_CAP_MINUTES - minutes_by_day.get(day, 0))


def available_starts(coach, client, duration_minutes, now, busy=None, minutes_by_day=None):
    """Every bookable start instant for the given duration, ascending.

    A start qualifies when it sits on the 15-min grid inside the lead/horizon
    window, the whole session fits inside bookable hours (working tz), the
    client's daily cap (client-tz day) has room, and nothing on the coach's
    calendar overlaps.
    """
    working_tz = working_timezone_for(coach)
    display_tz = display_timezone_for(client, working_tz)
    window_start, window_end = booking_window(now)
    if busy is None:
        busy = coach_busy_intervals(coach, window_start, window_end, working_tz)
    if minutes_by_day is None:
        minutes_by_day = panic_minutes_by_client_day(client, working_tz, display_tz)

    starts = []
    cursor = window_start
    step = timedelta(minutes=PANIC_SLOT_MINUTES)
    session = timedelta(minutes=duration_minutes)
    while cursor <= window_end:
        if is_within_bookable_hours(cursor, duration_minutes, working_tz):
            day = cursor.astimezone(display_tz).date()
            if duration_minutes <= remaining_minutes_for_day(minutes_by_day, day) and not overlaps_any(
                cursor, cursor + session, busy
            ):
                starts.append(cursor)
        cursor += step
    return starts


def next_policy_open_at(now, duration_minutes, working_tz):
    """Earliest grid instant ≥ now+lead inside bookable hours, ignoring the
    horizon, conflicts, and cap. Used to name the next bookable day when the
    window ∩ 8-5 M-F intersection is empty (e.g. Friday evening → Monday)."""
    cursor, _ = booking_window(now)
    step = timedelta(minutes=PANIC_SLOT_MINUTES)
    limit = cursor + timedelta(days=8)  # any weekend gap resolves well within this
    while cursor <= limit:
        if is_within_bookable_hours(cursor, duration_minutes, working_tz):
            return cursor
        cursor += step
    return None


def nearest_alternatives(requested_start, starts, limit=3):
    """The closest conflict-free starts to what the client asked for."""
    return sorted(starts, key=lambda start: abs(start - requested_start))[:limit]


def format_when(instant, tz):
    """Human, calm: 'Friday, July 31 at 2:00 pm EDT'."""
    local = instant.astimezone(tz)
    hour = local.hour % 12 or 12
    meridiem = "am" if local.hour < 12 else "pm"
    tz_name = local.tzname() or ""
    return f"{local.strftime('%A, %B')} {local.day} at {hour}:{local.minute:02d} {meridiem} {tz_name}".strip()


def cap_reset_text(display_tz, now):
    """Warm language naming when the daily cap comes back."""
    tz_name = now.astimezone(display_tz).tzname() or "your time"
    return (
        f"Your minutes reset at midnight ({tz_name}), so a fresh "
        f"{PANIC_DAILY_CAP_MINUTES} arrives with each new day."
    )
