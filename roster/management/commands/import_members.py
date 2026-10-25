import csv

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from roster.forms import FirstSectionAndFlagForm
from roster.models import Member, Section

REQUIRED_COLUMNS = ["name", "section"]
# RO-5: the Praise Team column accepts these; blank means no.
YES = {"yes", "y", "true", "1"}
NO = {"no", "n", "false", "0", ""}


class Command(BaseCommand):
    help = "RO-5: one-time import of members from a CSV file (columns: name, section, praise_team, phone, email, notes)."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Path to the CSV file (keep it in the git-ignored private-data/ folder)")

    def handle(self, *args, path, **options):
        rows = self.read_rows(path)
        # Check every row before saving any, so one typo never leaves a half-imported roster.
        forms, problems = self.check_rows(rows)
        if problems:
            # Business rules: personal data stays out of logs, so each problem is a line number and a fixed
            # reason, never the row's name, email or phone.
            raise CommandError("Nothing was imported. Fix these rows and run it again:\n" + "\n".join(problems))
        with transaction.atomic():
            for form in forms:
                member = form.save()
                # RO-5: Active, with their section and Praise Team flag, all dated today (US Eastern).
                member.start_history(
                    section=form.cleaned_data["initial_section"],
                    praise_team=form.cleaned_data["initial_praise_team"],
                )
        # Counts only, for the same privacy reason.
        self.stdout.write(f"Imported {len(forms)} members.")

    def read_rows(self, path):
        """The file's rows as (line number, dict of cleaned-up column names to text)."""
        try:
            # utf-8-sig quietly drops the invisible marker Excel puts at the start of a CSV.
            with open(path, newline="", encoding="utf-8-sig") as file:
                reader = csv.DictReader(file)
                columns = [(name or "").strip().lower() for name in reader.fieldnames or []]
                missing = [name for name in REQUIRED_COLUMNS if name not in columns]
                if missing:
                    raise CommandError(f"The file needs a header row with these columns: {', '.join(missing)}.")
                reader.fieldnames = columns
                # reader.line_num is the file line the row ended on, so it stays right when a note spans lines.
                return [(reader.line_num, row) for row in reader]
        except FileNotFoundError:
            raise CommandError(f"File not found: {path}")
        except UnicodeDecodeError:
            raise CommandError("The file isn't UTF-8 text. In Excel, use Save As > CSV UTF-8.")

    def check_rows(self, rows):
        """Validate each row with the Add page's own form, so the two share the same rules."""
        sections = {label.lower(): value for value, label in Section.choices}
        # Names compare ignoring case, so a rerun (or a repeat inside the file) can't duplicate a person.
        taken = {name.casefold() for name in Member.objects.values_list("name", flat=True)}
        forms, problems = [], []
        for line, row in rows:
            cell = lambda column: (row.get(column) or "").strip()
            reasons = []
            section = sections.get(cell("section").lower())
            if section is None:
                reasons.append("section must be Soprano, Alto, Tenor or Bass")
            flag = cell("praise_team").lower()
            if flag not in YES | NO:
                reasons.append("praise_team must be yes or no")
            form = FirstSectionAndFlagForm(
                {
                    "name": cell("name"),
                    "phone": cell("phone"),
                    "email": cell("email"),
                    "notes": cell("notes"),
                    "initial_section": section,
                    "initial_praise_team": flag in YES,
                }
            )
            form.is_valid()
            for field, errors in form.errors.as_data().items():
                if field in ("initial_section", "initial_praise_team"):
                    continue  # already reported above, in the file's own column names
                required = any(error.code == "required" for error in errors)
                reasons.append(f"{field} is required" if required else f"{field} is not valid")
            name = cell("name").casefold()
            if name:
                if name in taken:
                    reasons.append("that name is already on the roster or earlier in the file")
                taken.add(name)
            if reasons:
                problems.append(f"line {line}: " + "; ".join(reasons))
            else:
                forms.append(form)
        return forms, problems
