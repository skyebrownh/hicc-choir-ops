from django import forms
from django.utils import timezone

from accounts.models import Section
from roster.models import Member, PraiseTeamChange, SectionChange, Status, StatusChange

# Component classes from tailwind/input.css; `input` is 44px tall with 16px text (NFR).
INPUT_CLASSES = "input"


class FirstSectionAndFlagForm(forms.ModelForm):
    """RO-1, RO-6: a member's own fields plus their first section and Praise Team flag, asked for on add only.

    The app's Add form and the Django admin's add form both build on this, so the two cannot drift.
    Later changes go through the change forms below, so editing a member never touches their history.
    """

    class Meta:
        model = Member
        # RO-1. The model's EmailField checks the email's format; name is required.
        fields = ["name", "phone", "email", "notes"]

    initial_section = forms.ChoiceField(choices=[("", "---------"), *Section.choices], label="Section")
    initial_praise_team = forms.BooleanField(required=False, label="On the Praise Team")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            del self.fields["initial_section"], self.fields["initial_praise_team"]


class MemberForm(FirstSectionAndFlagForm):
    # RO-2: only on the add page. Left out means Active.
    initial_status = forms.ChoiceField(choices=Status.choices, initial=Status.ACTIVE, label="Status", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            del self.fields["initial_status"]
        else:
            # RO-2: Status, Section and Praise Team sit right above Notes, since they are chosen together.
            self.order_fields(["name", "phone", "email", "initial_status", "initial_section", "initial_praise_team", "notes"])
        for name, field in self.fields.items():
            if name == "initial_praise_team":
                field.widget.attrs["class"] = "size-6 accent-indigo-600"
            else:
                field.widget.attrs["class"] = INPUT_CLASSES
        self.fields["phone"].widget.attrs["autocomplete"] = "off"
        self.fields["notes"].widget.attrs["rows"] = 3


class DatedChangeForm(forms.ModelForm):
    """RO-2, RO-6: record one change with the date it took effect. The three history forms share this.

    A subclass names its model and value field in `Meta`. The member is set on the instance up front
    (see the views) so the model's "must change" check can see their history.
    """

    class Meta:
        widgets = {"effective_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = INPUT_CLASSES
        # US Eastern "today" (settings.TIME_ZONE), not the server's UTC date.
        # (Set on `initial`, not the field: a form built on an instance starts from the instance's empty date.)
        if self.initial.get("effective_on") is None:
            self.initial["effective_on"] = timezone.localdate()


class StatusChangeForm(DatedChangeForm):
    class Meta(DatedChangeForm.Meta):
        model = StatusChange
        fields = ["status", "effective_on"]
        labels = {"status": "New status", "effective_on": "Starting on"}


class SectionChangeForm(DatedChangeForm):
    class Meta(DatedChangeForm.Meta):
        model = SectionChange
        fields = ["section", "effective_on"]
        labels = {"section": "New section", "effective_on": "Starting on"}


class PraiseTeamChangeForm(DatedChangeForm):
    # RO-6: a Yes/No choice reads better than a lone checkbox here, where unticked means "leaves the team".
    praise_team = forms.TypedChoiceField(
        choices=[("yes", "Yes, on the Praise Team"), ("no", "No, not on the Praise Team")],
        coerce=lambda value: value == "yes",
        label="Praise Team",
    )

    class Meta(DatedChangeForm.Meta):
        model = PraiseTeamChange
        fields = ["praise_team", "effective_on"]
        labels = {"effective_on": "Starting on"}
