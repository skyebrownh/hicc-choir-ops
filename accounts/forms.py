from django import forms


class EmailForm(forms.Form):
    email = forms.EmailField(label="Your email address")


class CodeForm(forms.Form):
    code = forms.CharField(
        label="6-digit code",
        max_length=6,
        strip=True,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code"}),
    )
