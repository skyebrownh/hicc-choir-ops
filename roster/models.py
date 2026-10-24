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
    def with_current_status(self):
        """RO-2: adds `status_now` (the latest change's status) to each member in the same query.

        Same ordering as Member.status_history(), so the list and the member's page agree.
        """
        latest = StatusChange.objects.filter(member=models.OuterRef("pk")).order_by("-effective_on", "-id")
        return self.annotate(status_now=models.Subquery(latest.values("status")[:1]))

    def visible_to(self, account):
        """RO-3: admins see every member; a section leader sees members of their own sections.

        Every view loads members through here, so a member a leader may not see is simply
        absent and `get_object_or_404` answers "not found" (SPEC.md, Business rules).
        """
        if account.is_admin:
            return self
        return self.filter(section__in=account.sections)


class Member(models.Model):
    """A choir member (SPEC.md, Member). Not the same as an Account: most members never sign in."""

    # RO-1: name, phone, email, section, Praise Team yes/no, and notes.
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    # For now plain fields; the section-and-Praise-Team history issue (#10) replaces them
    # with dated changes (RO-6).
    section = models.CharField(max_length=10, choices=Section.choices)
    praise_team = models.BooleanField(default=False)
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


class StatusChange(models.Model):
    """RO-2: one status, with the date it took effect. A member's status is their latest change."""

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="status_changes")
    status = models.CharField(max_length=10, choices=Status.choices)
    effective_on = models.DateField()

    def __str__(self):
        return f"{self.member}: {self.get_status_display()} from {self.effective_on}"

    def clean(self):
        """RO-2: a change must actually change the status.

        It is compared with the change in effect on its date and with the next later one
        (which it would otherwise make pointless). Living on the model, the rule holds for
        the app's form and the Django admin alike.
        """
        super().clean()
        if not self.member_id or not self.effective_on or not self.status:
            return  # Other field errors are reported already.
        # RO-2: a past or today's date only, in US Eastern time. A future change would
        # otherwise become "current" before its date arrives.
        if self.effective_on > timezone.localdate():
            raise ValidationError({"effective_on": "The date can't be in the future."})
        # Sort key mirrors the history order: by date, then by when it was entered.
        # A row not saved yet counts as entered last, so it follows same-date rows.
        others = sorted(
            self.member.status_changes.exclude(pk=self.pk), key=lambda c: (c.effective_on, c.pk)
        )
        mine = (self.effective_on, self.pk or float("inf"))
        before = [c for c in others if (c.effective_on, c.pk) < mine]
        after = [c for c in others if (c.effective_on, c.pk) > mine]
        if before and before[-1].status == self.status:
            raise ValidationError(
                {"status": f"{self.member} is already {self.get_status_display()} on {date_format(self.effective_on)}."}
            )
        if after and after[0].status == self.status:
            raise ValidationError(
                {
                    "status": f"The next change, on {date_format(after[0].effective_on)}, is also "
                    f"{self.get_status_display()}, so this one would change nothing."
                }
            )
