from django.db import models

from accounts.models import Section


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
