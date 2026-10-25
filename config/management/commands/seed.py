from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import Account, Role
from roster.models import Member, PraiseTeamChange, SectionChange, StatusChange

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
    # RO-4: one on a break and one inactive, so the roster's status filter has something to find.
    ("Beth Rowe", "alto", False),
    ("Ian Stone", "tenor", False),
]
# RO-4: everyone else is Active.
OTHER_STATUSES = {"Beth Rowe": "on_break", "Ian Stone": "inactive"}


def seed_basic():
    today = timezone.localdate()
    for name, section, praise_team in BASIC_MEMBERS:
        slug = name.lower().replace(" ", ".")
        member = Member.objects.create(name=name, email=f"{slug}@example.com", phone="555-0100")
        # RO-6: everyone's section and Praise Team flag start today, like a member added or migrated today.
        # Two members have a little history behind them, so the history page has something to show:
        # Tim Hayes was an Alto until 30 days ago, and Amy Walker joined the Praise Team 30 days ago.
        if name == "Tim Hayes":
            SectionChange.objects.create(member=member, section="alto", effective_on=today - timedelta(days=90))
            SectionChange.objects.create(member=member, section=section, effective_on=today - timedelta(days=30))
        else:
            SectionChange.objects.create(member=member, section=section, effective_on=today)
        if name == "Amy Walker":
            PraiseTeamChange.objects.create(member=member, praise_team=False, effective_on=today - timedelta(days=90))
            PraiseTeamChange.objects.create(member=member, praise_team=True, effective_on=today - timedelta(days=30))
        else:
            PraiseTeamChange.objects.create(member=member, praise_team=praise_team, effective_on=today)
        # RO-2: everyone starts today (Active, except the two in OTHER_STATUSES), like a member added or migrated today. Amy Walker has a break behind her, so the history list has
        # something to show: Active, then On Break, then back to Active.
        if name == "Amy Walker":
            for status, days_ago in [("active", 90), ("on_break", 60), ("active", 0)]:
                StatusChange.objects.create(member=member, status=status, effective_on=today - timedelta(days=days_ago))
        else:
            StatusChange.objects.create(member=member, status=OTHER_STATUSES.get(name, "active"), effective_on=today)
    # For trying the section-leader view by hand. The sign-in code prints in the server console.
    # AC-5: each leader is a member in one of their sections, as real leaders are.
    Account.objects.create_user("alto.leader@example.com", sections=["alto"], member=Member.objects.get(name="Alice Grant"))
    Account.objects.create_user(
        "tenor.leader@example.com", sections=["tenor", "bass"], member=Member.objects.get(name="Tom Fisher")
    )
    # AC-6: like the director, an admin who is not a choir member. Admins survive a reseed, so create it only once.
    if not Account.objects.filter(email="director@example.com").exists():
        Account.objects.create_user("director@example.com", role=Role.ADMIN)


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
