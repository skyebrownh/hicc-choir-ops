from django.core.management.base import BaseCommand

from roster.events import create_upcoming_events


class Command(BaseCommand):
    help = "AT-1: create the Wednesday, Saturday and Sunday events for this week and the next 4. Safe to rerun."

    def handle(self, *args, **options):
        count = create_upcoming_events()
        self.stdout.write(f"Created {count} {'event' if count == 1 else 'events'}.")
