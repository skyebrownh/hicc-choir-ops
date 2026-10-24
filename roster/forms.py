from django import forms

from roster.models import Member

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
