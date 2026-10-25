from django import forms
from django.db.models import Q

from accounts.models import Account, Section
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # AC-5: a member has at most one account, so offer only those without one (plus this account's own).
        self.fields["member"].queryset = Member.objects.filter(
            Q(account__isnull=True) | Q(account=self.instance.pk)
        ).order_by("name")
        self.fields["email"].widget.attrs["class"] = "input"
        self.fields["role"].widget.attrs["class"] = "select"
        self.fields["member"].widget.attrs["class"] = "select"
