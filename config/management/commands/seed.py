from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Account, Role
from roster.models import Member

# Fake names only, on example.com: this is development data and must never hold real people.
BASIC_MEMBERS = [
    # (name, section, on the Praise Team)
    ("Sophie Reed", "soprano", True),
    ("Sarah Lane", "soprano", False),
    ("Samantha Cole", "soprano", False),
    ("Alice Grant", "alto", True),
    ("Amy Walker", "alto", False),
    ("Anna Brooks", "alto", False),
    ("Tom Fisher", "tenor", True),
    ("Tim Hayes", "tenor", False),
    ("Ted Morgan", "tenor", False),
    ("Ben Carter", "bass", False),
    ("Bill Dixon", "bass", True),
    ("Bob Ellis", "bass", False),
]


def seed_basic():
    for name, section, praise_team in BASIC_MEMBERS:
        slug = name.lower().replace(" ", ".")
        Member.objects.create(
            name=name,
            section=section,
            praise_team=praise_team,
            email=f"{slug}@example.com",
            phone="555-0100",
        )
    # For trying the section-leader view by hand. The sign-in code prints in the server console.
    Account.objects.create_user("alto.leader@example.com", sections=["alto"])
    Account.objects.create_user("tenor.leader@example.com", sections=["tenor", "bass"])


SCENARIOS = {"basic": seed_basic}


class Command(BaseCommand):
    help = "Reset the local database to a known scenario of fake data. Admin accounts are kept."

    def add_arguments(self, parser):
        parser.add_argument("scenario", help=f"One of: {', '.join(SCENARIOS)}")

    def handle(self, *args, scenario, **options):
        # Wipes data, so only ever on a developer's machine: production runs with DEBUG off.
        if not settings.DEBUG:
            raise CommandError("seed deletes data, so it only runs with DEBUG=true.")
        if scenario not in SCENARIOS:
            raise CommandError(f"Unknown scenario '{scenario}'. Known scenarios: {', '.join(SCENARIOS)}.")
        # All or nothing, so a failure part-way never leaves a half-wiped database.
        with transaction.atomic():
            Member.objects.all().delete()
            Account.objects.exclude(role=Role.ADMIN).delete()
            SCENARIOS[scenario]()
        if options["verbosity"]:
            self.stdout.write(self.style.SUCCESS(f"Seeded the '{scenario}' scenario."))
