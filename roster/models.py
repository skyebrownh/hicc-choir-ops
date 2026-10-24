from django.db import models

from accounts.models import Section


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

    def __str__(self):
        return self.name
