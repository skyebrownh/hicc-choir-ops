from urllib.parse import urlencode

from django import forms
from django.db.models import Q
from django.utils import timezone

from accounts.models import Section
from roster.models import Member, PraiseTeamChange, SectionChange, Status, StatusChange

# Component classes from tailwind/input.css; `input` is 44px tall with 16px text (NFR).
INPUT_CLASSES = "input"
# Dropdowns use `select` instead: same size and text, plus room for the drawn arrow (see _select_chevron.html).
SELECT_CLASSES = "select"


def widget_classes(widget):
    """The component class for a form widget: dropdowns get the arrow-ready look, everything else the text-input look."""
    return SELECT_CLASSES if isinstance(widget, forms.Select) else INPUT_CLASSES


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
                field.widget.attrs["class"] = widget_classes(field.widget)
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
            field.widget.attrs["class"] = widget_classes(field.widget)
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


class MemberFilterForm(forms.Form):
    """RO-4: the roster's filters, read from the page's query string (GET) or, when it has none, from
    the copy the view remembers in the person's session (see `member_list`).

    A value that isn't one of the choices is dropped by validation, so a mistyped, out-of-reach or
    since-removed value just means "no filter" on that field instead of an error page.
    """

    # RO-4: the query-string keys the view treats as "these are my filters".
    FIELD_NAMES = ("section", "status", "praise_team")

    # RO-4: "" is every field's default. Status's default hides Inactive members, because that group can grow large.
    STATUS_CHOICES = [
        ("", "Active and On Break"),
        (Status.ACTIVE.value, "Active"),
        (Status.ON_BREAK.value, "On Break"),
        (Status.INACTIVE.value, "Inactive"),
        ("all", "Everyone"),
    ]

    section = forms.ChoiceField(required=False, label="Section")
    status = forms.ChoiceField(choices=STATUS_CHOICES, required=False, label="Status")
    praise_team = forms.ChoiceField(
        choices=[("", "Any"), ("yes", "On the Praise Team"), ("no", "Not on the Praise Team")],
        required=False,
        label="Praise Team",
    )

    def __init__(self, data, account):
        super().__init__(data)
        # RO-3: offer only the sections this person can see. A leader with one section has nothing to pick,
        # so the field goes (the list is already limited to that section by `visible_to`).
        sections = list(Section.choices) if account.is_admin else [c for c in Section.choices if c[0] in account.sections]
        if len(sections) > 1:
            self.fields["section"].choices = [("", "All sections"), *sections]
        else:
            del self.fields["section"]
        for field in self.fields.values():
            field.widget.attrs["class"] = widget_classes(field.widget)

    def _value(self, name):
        # RO-4: invalid values are missing from cleaned_data, which reads as the default.
        self.is_valid()
        return self.cleaned_data.get(name, "")

    @property
    def hiding_inactive(self):
        # RO-4: true when the default status choice is in force, so the page can say Inactive members are hidden.
        return self._value("status") == ""

    @property
    def changed_from_default(self):
        # RO-4: true once any filter differs from the default view, so the page offers "Reset".
        return any(self._value(name) for name in self.fields)

    def everyone_query(self):
        """RO-4: the query string for "Show everyone": the same filters, with every status."""
        chosen = {name: self._value(name) for name in ("section", "praise_team") if self._value(name)}
        return urlencode({**chosen, "status": "all"})

    def filter(self, members):
        """RO-4: narrows a queryset that already has `status_now` (see `with_current_status`)."""
        if self._value("section"):
            members = members.filter(section_now=self._value("section"))
        praise_team = self._value("praise_team")
        if praise_team == "yes":
            members = members.filter(praise_team_now=True)
        elif praise_team == "no":
            # RO-6: a member with no Praise Team change at all counts as not on it (see Member.current_praise_team).
            members = members.filter(Q(praise_team_now=False) | Q(praise_team_now__isnull=True))
        status = self._value("status")
        if status == "":
            # RO-2: a member with no status at all (not expected in the app) stays visible rather than vanishing:
            # in SQL, NULL is never "not equal" to anything, so it needs asking for.
            return members.filter(~Q(status_now=Status.INACTIVE) | Q(status_now__isnull=True))
        if status != "all":
            return members.filter(status_now=status)
        return members
