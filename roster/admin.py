from django import forms
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.widgets import UnfoldAdminSelectWidget, UnfoldBooleanWidget

from accounts.models import Section
from roster.models import Member, PraiseTeamChange, SectionChange, Status, StatusChange


class MemberChangeAdmin(ModelAdmin):
    """RO-2, RO-6: for fixing mistakes in a member's history of status, section or Praise Team.

    Only reachable through a member (their page links here, filtered to them): there is no
    reason to look at every member's changes at once, so it is left off the admin's home page
    and menu, and the page without a member sends you to the Members list.
    """

    ordering = ["-effective_on", "-id"]

    def has_module_permission(self, request):
        # Hides it from the admin home page and sidebar; its pages still work by link.
        return False

    def _changelist_url(self):
        return reverse(f"admin:roster_{self.model._meta.model_name}_changelist")

    def changelist_view(self, request, extra_context=None):
        # RO-2: no member given means someone typed the address; send them to pick a member.
        if "member__id__exact" not in request.GET:
            return redirect(reverse("admin:roster_member_changelist"))
        return super().changelist_view(request, extra_context)

    def _back_to_member(self, obj):
        return redirect(f"{self._changelist_url()}?member__id__exact={obj.member_id}")

    def response_post_save_add(self, request, obj):
        return self._back_to_member(obj)

    def response_post_save_change(self, request, obj):
        return self._back_to_member(obj)


@admin.register(StatusChange)
class StatusChangeAdmin(MemberChangeAdmin):
    list_display = ["effective_on", "status", "member"]


@admin.register(SectionChange)
class SectionChangeAdmin(MemberChangeAdmin):
    list_display = ["effective_on", "section", "member"]


@admin.register(PraiseTeamChange)
class PraiseTeamChangeAdmin(MemberChangeAdmin):
    list_display = ["effective_on", "praise_team", "member"]


class MemberAddForm(forms.ModelForm):
    """RO-6: the admin's add form also asks for the first section and Praise Team flag, as the app's does."""

    initial_section = forms.ChoiceField(
        choices=[("", "---------"), *Section.choices], label="Section", widget=UnfoldAdminSelectWidget
    )
    initial_praise_team = forms.BooleanField(required=False, label="On the Praise Team", widget=UnfoldBooleanWidget)

    class Meta:
        model = Member
        fields = ["name", "phone", "email", "notes"]


@admin.register(Member)
class MemberAdmin(ModelAdmin):
    list_display = ["name"]
    search_fields = ["name", "email"]
    readonly_fields = ["status_changes_link", "section_changes_link", "praise_team_changes_link"]

    def get_form(self, request, obj=None, **kwargs):
        # RO-6: the first section and flag are asked for on add only; later changes go through the history pages.
        if obj is None:
            kwargs["form"] = MemberAddForm
        return super().get_form(request, obj, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return ["name", "phone", "email", "initial_section", "initial_praise_team", "notes"]
        return [
            "name", "phone", "email", "notes",
            "status_changes_link", "section_changes_link", "praise_team_changes_link",
        ]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # RO-2, RO-6: every member has a status, section and Praise Team flag, as with the app's Add form:
        # a new member starts Active today, in the section and with the flag the form gave. Editing leaves the history alone.
        if not change:
            today = timezone.localdate()
            StatusChange.objects.create(member=obj, status=Status.ACTIVE, effective_on=today)
            SectionChange.objects.create(member=obj, section=form.cleaned_data["initial_section"], effective_on=today)
            PraiseTeamChange.objects.create(
                member=obj, praise_team=form.cleaned_data["initial_praise_team"], effective_on=today
            )

    def _link(self, member, model_name, related, singular, plural):
        if not member.pk:
            return "Save the member first."
        url = reverse(f"admin:roster_{model_name}_changelist")
        count = getattr(member, related).count()
        noun = singular if count == 1 else plural
        return format_html('<a href="{}?member__id__exact={}">{} {}: view and fix</a>', url, member.pk, count, noun)

    @admin.display(description="Status changes")
    def status_changes_link(self, member):
        return self._link(member, "statuschange", "status_changes", "status change", "status changes")

    @admin.display(description="Section changes")
    def section_changes_link(self, member):
        return self._link(member, "sectionchange", "section_changes", "section change", "section changes")

    @admin.display(description="Praise Team changes")
    def praise_team_changes_link(self, member):
        return self._link(member, "praiseteamchange", "praise_team_changes", "Praise Team change", "Praise Team changes")
