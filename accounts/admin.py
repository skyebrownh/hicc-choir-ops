from django import forms
from django.contrib import admin
from unfold.admin import ModelAdmin

from accounts.models import Account, Section


class AccountForm(forms.ModelForm):
    # Sections as checkboxes, so nobody types a Postgres array.
    sections = forms.MultipleChoiceField(
        choices=Section.choices, widget=forms.CheckboxSelectMultiple, required=False
    )

    class Meta:
        model = Account
        fields = ["email", "role", "member", "sections"]


@admin.register(Account)
class AccountAdmin(ModelAdmin):
    # Accounts are normally managed on the app's own Accounts page; this is Skye's fallback for fixing data.
    form = AccountForm
    list_display = ["email", "role", "member", "sections"]
    search_fields = ["email"]
