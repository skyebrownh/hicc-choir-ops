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
        fields = ["email", "role", "sections"]


@admin.register(Account)
class AccountAdmin(ModelAdmin):
    # Until the account pages (#13), this is how accounts are created.
    form = AccountForm
    list_display = ["email", "role", "sections"]
    search_fields = ["email"]
