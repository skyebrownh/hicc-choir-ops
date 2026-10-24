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

    # RO-2: only on the add page. Left out means Active. Later changes go through StatusChangeForm, so editing
    # a member never touches their status history.
    initial_status = forms.ChoiceField(choices=Status.choices, initial=Status.ACTIVE, label="Status", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            del self.fields["initial_status"]
        if "initial_status" in self.fields:
            # RO-2: Status sits right above Section, since they are chosen together.
            self.order_fields(["name", "phone", "email", "initial_status", "section"])
        for name, field in self.fields.items():
            if name == "praise_team":
                field.widget.attrs["class"] = "size-6 accent-indigo-600"
            else:
                field.widget.attrs["class"] = INPUT_CLASSES
        if "initial_status" in self.fields:
            self.fields["initial_status"].widget.attrs["class"] = INPUT_CLASSES
        self.fields["phone"].widget.attrs["autocomplete"] = "off"
        self.fields["notes"].widget.attrs["rows"] = 3


class StatusChangeForm(forms.ModelForm):
    """RO-2: record one status change with the date it took effect."""

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
        # (Set on `initial`, not the field: a form built on an instance starts from the instance's empty date.)
        if self.initial.get("effective_on") is None:
            self.initial["effective_on"] = timezone.localdate()
