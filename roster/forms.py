from django import forms
from django.utils import timezone

from roster.models import Member, Status, StatusChange

# Component classes from tailwind/input.css; `input` is 44px tall with 16px text (NFR).
INPUT_CLASSES = "input"


class MemberForm(forms.ModelForm):
    class Meta:
        model = Member
        # RO-1. The model's EmailField checks the email's format; name and section are required.
        fields = ["name", "phone", "email", "section", "praise_team", "notes"]
        labels = {"praise_team": "On the Praise Team"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name == "praise_team":
                field.widget.attrs["class"] = "size-6 accent-indigo-600"
            else:
                field.widget.attrs["class"] = INPUT_CLASSES
        self.fields["phone"].widget.attrs["autocomplete"] = "off"
        self.fields["notes"].widget.attrs["rows"] = 3


class StatusChangeForm(forms.ModelForm):
    class Meta:
        model = StatusChange
        fields = ["status", "effective_on"]
        labels = {"status": "New status", "effective_on": "Starting on"}
        widgets = {"effective_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = INPUT_CLASSES
        # US Eastern "today" (settings.TIME_ZONE), not the server's UTC date.
        self.fields["effective_on"].initial = timezone.localdate

    def clean_effective_on(self):
        # RO-2: a past or today's date only. There is deliberately no same-date check:
        # two changes on one date are allowed and the one entered last counts.
        value = self.cleaned_data["effective_on"]
        if value > timezone.localdate():
            raise forms.ValidationError("The date can't be in the future.")
        return value
