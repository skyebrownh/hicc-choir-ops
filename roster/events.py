import calendar
from datetime import timedelta

from django.utils import timezone

from roster.models import Event

# AT-1: the current week plus the next 4.
WEEKS_AHEAD = 5

# AT-1: (kind, weekday, who is expected). A week starts on Monday (weekday 0), so a weekday is also its days after Monday.
WEEKLY_SCHEDULE = [
    (Event.Kind.WEDNESDAY, calendar.WEDNESDAY, Event.Expected.PRAISE_TEAM),
    (Event.Kind.SATURDAY, calendar.SATURDAY, Event.Expected.EVERYONE),
    # One event covers both services (SPEC.md, Business rules).
    (Event.Kind.SUNDAY, calendar.SUNDAY, Event.Expected.EVERYONE),
]


def create_upcoming_events(today=None):
    """AT-1: creates this week's and the next 4 weeks' weekly events, and returns how many were new.

    A week runs Monday to Sunday. `today` defaults to the US Eastern date (settings.TIME_ZONE), so a late
    Sunday night still belongs to the week that is ending. Safe to rerun: `get_or_create` finds an event
    that exists, including a canceled one, and leaves it exactly as it is (AT-3).
    """
    today = today or timezone.localdate()
    monday = today - timedelta(days=today.weekday())
    created = 0
    for week in range(WEEKS_AHEAD):
        for kind, weekday, expected in WEEKLY_SCHEDULE:
            day = monday + timedelta(weeks=week, days=weekday)
            _, is_new = Event.objects.get_or_create(date=day, kind=kind, defaults={"expected": expected})
            created += is_new
    return created


def created_message(count):
    """AT-1: "Created 3 events." for the command's output and the button's message alike."""
    return f"Created {count} {'event' if count == 1 else 'events'}."
