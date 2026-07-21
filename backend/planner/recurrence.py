"""Pure expansion of recurring events into occurrence dates.

A recurring event occurs from its base ``event_date`` through
``recurrence_until`` (inclusive; validation guarantees it is set). Monthly
events fall on the base date's day-of-month; months without that day
(e.g. the 31st in February) are skipped.
"""
from datetime import timedelta

from .models import Event


def _add_months(day, months):
    total = day.month - 1 + months
    year = day.year + total // 12
    month = total % 12 + 1
    try:
        return day.replace(year=year, month=month)
    except ValueError:  # that month has no such day (e.g. Feb 31)
        return None


def expand_event_dates(event_date, recurrence_type, recurrence_until, range_start=None, range_end=None):
    """Return the dates an event occurs on, oldest first.

    Non-recurring events yield just their base date. Recurring events yield
    every matching date from ``event_date`` through ``recurrence_until``
    (inclusive). ``range_start``/``range_end`` (inclusive) clip the output.
    """

    def in_range(day):
        if range_start and day < range_start:
            return False
        if range_end and day > range_end:
            return False
        return True

    is_recurring = (
        recurrence_type
        and recurrence_type != Event.RecurrenceChoices.NONE
        and recurrence_until is not None
    )
    if not is_recurring:
        return [event_date] if in_range(event_date) else []

    dates = []
    if recurrence_type == Event.RecurrenceChoices.MONTHLY:
        months = 0
        while True:
            day = _add_months(event_date, months)
            months += 1
            if day is None:
                continue  # skipped month; later months still have the day
            if day > recurrence_until:
                break
            if in_range(day):
                dates.append(day)
        return dates

    step = timedelta(days=1 if recurrence_type == Event.RecurrenceChoices.DAILY else 7)
    day = event_date
    while day <= recurrence_until:
        if in_range(day):
            dates.append(day)
        day += step
    return dates
