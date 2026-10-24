from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from roster.models import Member, StatusChange


@admin.register(StatusChange)
class StatusChangeAdmin(ModelAdmin):
    """RO-2: for fixing mistakes in a member's status history.

    Only reachable through a member (their page links here, filtered to them): there is no
    reason to look at every member's changes at once, so it is left off the admin's home page
    and menu, and the page without a member sends you to the Members list.
    """

    list_display = ["effective_on", "status", "member"]
    ordering = ["-effective_on", "-id"]

    def has_module_permission(self, request):
        # Hides it from the admin home page and sidebar; its pages still work by link.
        return False

    def changelist_view(self, request, extra_context=None):
        if "member__id__exact" not in request.GET:
            return redirect(reverse("admin:roster_member_changelist"))
        return super().changelist_view(request, extra_context)

    def _back_to_member(self, obj):
        url = reverse("admin:roster_statuschange_changelist")
        return redirect(f"{url}?member__id__exact={obj.member_id}")

    def response_post_save_add(self, request, obj):
        return self._back_to_member(obj)

    def response_post_save_change(self, request, obj):
        return self._back_to_member(obj)


@admin.register(Member)
class MemberAdmin(ModelAdmin):
    list_display = ["name", "section", "praise_team"]
    list_filter = ["section", "praise_team"]
    search_fields = ["name", "email"]
    readonly_fields = ["status_changes_link"]

    @admin.display(description="Status changes")
    def status_changes_link(self, member):
        if not member.pk:
            return "Save the member first."
        url = reverse("admin:roster_statuschange_changelist")
        count = member.status_changes.count()
        noun = "status change" if count == 1 else "status changes"
        return format_html('<a href="{}?member__id__exact={}">{} {}: view and fix</a>', url, member.pk, count, noun)
