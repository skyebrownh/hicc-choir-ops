from django import forms
from django.db.models import Q

from accounts.models import Account, Role, Section
from roster.models import Member


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


class AccountForm(forms.ModelForm):
    """AC-5, AC-6: give a member (or nobody, for an admin) a way to sign in. Add and edit share this."""

    # Sections as checkboxes, so nobody types a Postgres array.
    sections = forms.MultipleChoiceField(
        choices=Section.choices, widget=forms.CheckboxSelectMultiple, required=False
    )
    member = forms.ModelChoiceField(queryset=Member.objects.none(), required=False, empty_label="No member")

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
        # AC-5: a member has at most one account, so offer only those without one (plus this account's own).
        self.fields["member"].queryset = Member.objects.filter(
            Q(account__isnull=True) | Q(account=self.instance.pk)
        ).order_by("name")
        self.fields["email"].widget.attrs["class"] = "input"
        self.fields["role"].widget.attrs["class"] = "select"
        self.fields["member"].widget.attrs["class"] = "select"
        self.fields["sections"].widget.attrs["class"] = "size-6 accent-indigo-600"

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
            # Also guarantees the last admin can't lose their access.
            self.add_error("role", "You can't take away your own admin access.")
        if role == Role.ADMIN:
            # AC-5: an admin sees every section, so submitted sections are ignored and the stored ones
            # stay, ready if they become a leader again.
            cleaned["sections"] = list(self.instance.sections)
        return cleaned
