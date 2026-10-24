from django import forms

from roster.models import Member

# NFR: 44px-tall tap targets and 16px text on every input.
INPUT_CLASSES = "block min-h-11 w-full rounded border border-gray-400 px-3 text-base"


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
                field.widget.attrs["class"] = "size-6"
            else:
                field.widget.attrs["class"] = INPUT_CLASSES
        self.fields["phone"].widget.attrs["autocomplete"] = "off"
        self.fields["notes"].widget.attrs["rows"] = 3
