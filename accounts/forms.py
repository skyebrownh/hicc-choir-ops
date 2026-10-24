from django import forms


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
