from django import forms
from django.db.models import Q

from accounts.models import Account, Role, Section
from roster.models import Member, Status


class EmailForm(forms.Form):
    email = forms.EmailField(
        label="Your email address",
        widget=forms.EmailInput(attrs={"class": "input", "autocomplete": "email", "autofocus": True}),
    )


class CodeForm(forms.Form):
    code = forms.CharField(
        label="6-digit code",
        max_length=6,
        strip=True,
        widget=forms.TextInput(
            attrs={"class": "input", "inputmode": "numeric", "autocomplete": "one-time-code", "autofocus": True}
        ),
    )


class MemberSelect(forms.Select):
    """A dropdown whose listed options can be greyed out and unselectable (`disabled_values`, as strings)."""

    disabled_values = frozenset()

    def create_option(self, name, value, *args, **kwargs):
        option = super().create_option(name, value, *args, **kwargs)
        if str(value) in self.disabled_values:
            option["attrs"]["disabled"] = True
        return option


class AccountForm(forms.ModelForm):
    """AC-5, AC-6: give a member (or nobody, for an admin) a way to sign in. Add and edit share this."""

    # AC-5: sections as checkboxes, so nobody types a Postgres array.
    sections = forms.MultipleChoiceField(
        choices=Section.choices, widget=forms.CheckboxSelectMultiple, required=False
    )
    member = forms.ModelChoiceField(
        queryset=Member.objects.none(), required=False, empty_label="No member", widget=MemberSelect
    )

    class Meta:
        model = Account
        fields = ["email", "role", "member", "sections"]

    def __init__(self, *args, acting_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.acting_user = acting_user
        if self.instance.pk:
            # AC-1: sign-in codes go to this address, so changing it would orphan whoever signs in with it.
            # A disabled field ignores whatever is posted and keeps the stored email.
            self.fields["email"].disabled = True
        self._set_member_choices()
        self.fields["email"].widget.attrs["class"] = "input"
        self.fields["role"].widget.attrs["class"] = "select"
        self.fields["member"].widget.attrs["class"] = "select"
        self.fields["sections"].widget.attrs["class"] = "size-6 accent-indigo-600"

    def _set_member_choices(self):
        """AC-5: the dropdown lists members grouped by section, so an admin can tell who is who.

        - A member with an account is shown but greyed out and unselectable: a member has at most one
          account, and hiding them would leave the admin wondering where they went.
        - Inactive members are left out (the page says so), unless this account already belongs to one,
          so editing it still works.
        - What the server accepts (`queryset`) is stricter than what is shown, so a hand-made request can't
          pick a greyed-out or hidden member either.
        """
        own = self.instance.member_id
        shown = Member.objects.with_current_status().filter(
            ~Q(status_now=Status.INACTIVE) | Q(status_now__isnull=True) | Q(pk=own)
        )
        self.fields["member"].queryset = shown.filter(Q(account__isnull=True) | Q(account=self.instance.pk))
        have_account = set(Account.objects.exclude(pk=self.instance.pk).values_list("member_id", flat=True))
        you = getattr(self.acting_user, "member_id", None)

        def label(member):
            # AC-8: your own member is marked "you"; a greyed-out one says why.
            notes = [text for applies, text in [(member.pk == you, "you"), (member.pk in have_account, "has an account")] if applies]
            return f"{member.name} ({', '.join(notes)})" if notes else member.name

        # AC-5: sections in the choir's usual order, then anyone with no section at all.
        sections = [*Section.values, None]
        groups = []
        for section in sections:
            members = sorted((m for m in shown if m.section_now == section), key=lambda m: m.name.lower())
            if members:
                heading = Section(section).label if section else "No section"
                groups.append((heading, [(m.pk, label(m)) for m in members]))
        widget = self.fields["member"].widget
        widget.disabled_values = frozenset(str(pk) for pk in have_account if pk)
        self.fields["member"].choices = [("", "No member"), *groups]

    @property
    def role_is_admin(self):
        # AC-5: decides whether the page starts with the section boxes hidden; the same rule the script applies on change.
        return self["role"].value() == Role.ADMIN

    def clean_email(self):
        email = self.cleaned_data["email"]
        # AC-5: sign-in matches emails ignoring case, so "Sophie@" and "sophie@" are the same address.
        others = Account.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if others.exists():
            raise forms.ValidationError("That email already has an account.")
        return email

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role")
        if role == Role.SECTION_LEADER:
            # AC-5, AC-6: only an admin may go without a member; a leader is a choir member with sections.
            if not cleaned.get("member"):
                self.add_error("member", "A section leader has to be a choir member.")
            if not cleaned.get("sections"):
                self.add_error("sections", "Pick at least one section.")
        if self.instance.pk and self.instance.pk == getattr(self.acting_user, "pk", None) and role != Role.ADMIN:
            # AC-5: also guarantees the last admin can't lose their access.
            self.add_error("role", "You can't take away your own admin access.")
        if role == Role.ADMIN:
            # AC-5: an admin sees every section, so submitted sections are ignored and the stored ones
            # stay, ready if they become a leader again.
            cleaned["sections"] = list(self.instance.sections)
        return cleaned
