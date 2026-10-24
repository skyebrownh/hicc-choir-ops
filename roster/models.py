from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.formats import date_format as _date_format

from accounts.models import Section


def date_format(value):
    # RO-2: one date style ("Jun 1, 2026") for the messages that name a date.
    return _date_format(value, "M j, Y")


class Status(models.TextChoices):
    ACTIVE = "active", "Active"
    ON_BREAK = "on_break", "On Break"
    INACTIVE = "inactive", "Inactive"


class MemberQuerySet(models.QuerySet):
    def _latest(self, change_model, field):
        # The latest change's value, with the same ordering as the Member.*_history() methods
        # so the list and the member's page agree.
        latest = change_model.objects.filter(member=models.OuterRef("pk")).order_by("-effective_on", "-id")
        return models.Subquery(latest.values(field)[:1])

    def with_current_status(self):
        """RO-2, RO-6: adds `status_now`, `section_now` and `praise_team_now` (each the latest change's value) in the same query."""
        return self.annotate(
            status_now=self._latest(StatusChange, "status"),
            section_now=self._latest(SectionChange, "section"),
            praise_team_now=self._latest(PraiseTeamChange, "praise_team"),
        )

    def visible_to(self, account):
        """RO-3: admins see every member; a section leader sees members of their own sections.

        Every view loads members through here, so a member a leader may not see is simply
        absent and `get_object_or_404` answers "not found" (SPEC.md, Business rules).
        """
        if account.is_admin:
            return self
        # RO-6: by the section they are in now, so a member who moved leaves their old leader's view.
        return self.annotate(section_now=self._latest(SectionChange, "section")).filter(section_now__in=account.sections)


class Member(models.Model):
    """A choir member (SPEC.md, Member). Not the same as an Account: most members never sign in."""

    # RO-1: name, phone, email, section, Praise Team yes/no, and notes. Section and Praise Team
    # are not fields here: each is the latest of its dated changes (RO-6), read through
    # `current_section` and `current_praise_team`.
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    notes = models.TextField(blank=True)

    objects = MemberQuerySet.as_manager()

    def __str__(self):
        return self.name

    def status_history(self):
        """RO-2: newest change first. Same-date changes are ordered by id, so the one entered last wins."""
        return self.status_changes.order_by("-effective_on", "-id")

    @property
    def current_status(self):
        """RO-2: the latest change. None only for a member with no change at all (not expected in the app)."""
        latest = self.status_history().first()
        return latest.status if latest else None

    @property
    def current_status_display(self):
        # RO-2: the label for the current status, for pages that show it.
        latest = self.status_history().first()
        return latest.get_status_display() if latest else ""

    def section_history(self):
        """RO-6: newest change first, same-date ties to the one entered last (like status_history)."""
        return self.section_changes.order_by("-effective_on", "-id")

    def section_on(self, day):
        """RO-6: the section on `day`: the latest change on or before it, or None before the first one."""
        latest = self.section_history().filter(effective_on__lte=day).first()
        return latest.section if latest else None

    @property
    def current_section(self):
        # RO-6: the latest change. None only for a member with no change at all (not expected in the app).
        latest = self.section_history().first()
        return latest.section if latest else None

    @property
    def current_section_display(self):
        # RO-6: the label for the current section, for pages that show it.
        latest = self.section_history().first()
        return latest.get_section_display() if latest else ""

    def praise_team_history(self):
        """RO-6: newest change first, same-date ties to the one entered last."""
        return self.praise_team_changes.order_by("-effective_on", "-id")

    def praise_team_on(self, day):
        """RO-6: whether they were on the Praise Team on `day`. No change on or before it means not on it."""
        latest = self.praise_team_history().filter(effective_on__lte=day).first()
        return latest.praise_team if latest else False

    @property
    def current_praise_team(self):
        # RO-6: the latest change; a member with none is not on the Praise Team.
        latest = self.praise_team_history().first()
        return latest.praise_team if latest else False


class DatedChange(models.Model):
    """RO-2, RO-6: a value for a member with the date it took effect. Their value is their latest change.

    Status, section and Praise Team all keep history this way, so the rules about dates
    ("not in the future", "must actually change something") are written once, here.
    """

    # The name of the field a subclass adds to hold its value ("status", "section", ...).
    value_field = None

    effective_on = models.DateField()

    class Meta:
        abstract = True

    def value_label(self):
        # How the value reads inside a message. Subclasses override this where the plain label reads oddly.
        return getattr(self, f"get_{self.value_field}_display")()

    def clean(self):
        """RO-2, RO-6: a change must actually change the value.

        It is compared with the change in effect on its date and with the next later one
        (which it would otherwise make pointless). Living on the model, the rule holds for
        the app's form and the Django admin alike.
        """
        super().clean()
        value = getattr(self, self.value_field)
        if not self.member_id or not self.effective_on or value in (None, ""):
            return  # Other field errors are reported already.
        # RO-2: a past or today's date only, in US Eastern time. A future change would
        # otherwise become "current" before its date arrives.
        if self.effective_on > timezone.localdate():
            raise ValidationError({"effective_on": "The date can't be in the future."})
        # Sort key mirrors the history order: by date, then by when it was entered.
        # A row not saved yet counts as entered last, so it follows same-date rows.
        others = sorted(
            type(self).objects.filter(member=self.member).exclude(pk=self.pk), key=lambda c: (c.effective_on, c.pk)
        )
        mine = (self.effective_on, self.pk or float("inf"))
        before = [c for c in others if (c.effective_on, c.pk) < mine]
        after = [c for c in others if (c.effective_on, c.pk) > mine]
        if before and getattr(before[-1], self.value_field) == value:
            raise ValidationError(
                {self.value_field: f"{self.member} is already {self.value_label()} on {date_format(self.effective_on)}."}
            )
        if after and getattr(after[0], self.value_field) == value:
            raise ValidationError(
                {
                    self.value_field: f"The next change, on {date_format(after[0].effective_on)}, is also "
                    f"{self.value_label()}, so this one would change nothing."
                }
            )


class StatusChange(DatedChange):
    """RO-2: one status, with the date it took effect. A member's status is their latest change."""

    value_field = "status"

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="status_changes")
    status = models.CharField(max_length=10, choices=Status.choices)

    def __str__(self):
        return f"{self.member}: {self.get_status_display()} from {self.effective_on}"


class SectionChange(DatedChange):
    """RO-6: one section, with the date it took effect. A member's section on a date is their latest change on or before it."""

    value_field = "section"

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="section_changes")
    section = models.CharField(max_length=10, choices=Section.choices)

    def __str__(self):
        return f"{self.member}: {self.get_section_display()} from {self.effective_on}"

    def value_label(self):
        return f"in {self.get_section_display()}"


class PraiseTeamChange(DatedChange):
    """RO-6: joining or leaving the Praise Team, with the date it took effect."""

    value_field = "praise_team"

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="praise_team_changes")
    praise_team = models.BooleanField()

    def __str__(self):
        return f"{self.member}: {self.value_label()} from {self.effective_on}"

    def get_praise_team_display(self):
        # The wording pages use for this value, in the same style as get_section_display().
        return "On the Praise Team" if self.praise_team else "Not on the Praise Team"

    def value_label(self):
        # Lower-case, for inside a sentence.
        return self.get_praise_team_display()[0].lower() + self.get_praise_team_display()[1:]
