from django.db import models

from accounts.models import Section


class Status(models.TextChoices):
    ACTIVE = "active", "Active"
    ON_BREAK = "on_break", "On Break"
    INACTIVE = "inactive", "Inactive"


class MemberQuerySet(models.QuerySet):
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
