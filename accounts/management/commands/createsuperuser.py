from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from accounts.models import Account


class Command(BaseCommand):
    """Replaces Django's `createsuperuser`, which insists on a password (AC-1: there are none)."""

    help = "Create an Admin account. Asks for an email address only."

    def add_arguments(self, parser):
        parser.add_argument("--email")
        # Accepted so scripts written for Django's command still work.
        parser.add_argument("--noinput", "--no-input", action="store_false", dest="interactive")

    def handle(self, *args, **options):
        email = options["email"]
        if not email:
            if not options["interactive"]:
                raise CommandError("Pass --email when using --noinput.")
            email = input("Email address: ").strip()
        try:
            validate_email(email)
        except ValidationError:
            raise CommandError("That isn't a valid email address.")
        if Account.objects.filter(email__iexact=email).exists():
            raise CommandError("An account with that email already exists.")
        Account.objects.create_superuser(email)
        if options["verbosity"]:
            self.stdout.write(f"Admin account created for {email}.")
