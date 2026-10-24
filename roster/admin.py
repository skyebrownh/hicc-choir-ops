from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from roster.models import Member, StatusChange


class StatusChangeInline(TabularInline):
    """RO-2: for fixing mistakes. The app's own screens only ever add changes."""

    model = StatusChange
    extra = 0


@admin.register(Member)
class MemberAdmin(ModelAdmin):
    inlines = [StatusChangeInline]
    list_display = ["name", "section", "praise_team"]
    list_filter = ["section", "praise_team"]
    search_fields = ["name", "email"]
