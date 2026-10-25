from datetime import timedelta

from django.utils import timezone

from roster.models import Event

# AT-1: the current week plus the next 4.
WEEKS_AHEAD = 5

# AT-1: (kind, days after Monday, who is expected).
WEEKLY_SCHEDULE = [
    (Event.Kind.WEDNESDAY, 2, Event.Expected.PRAISE_TEAM),
    (Event.Kind.SATURDAY, 5, Event.Expected.EVERYONE),
    # One event covers both services (SPEC.md, Business rules).
    (Event.Kind.SUNDAY, 6, Event.Expected.EVERYONE),
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
        for kind, offset, expected in WEEKLY_SCHEDULE:
            day = monday + timedelta(weeks=week, days=offset)
            _, is_new = Event.objects.get_or_create(date=day, kind=kind, defaults={"expected": expected})
            created += is_new
    return created
