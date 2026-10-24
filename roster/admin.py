from django.contrib import admin
from unfold.admin import ModelAdmin

from roster.models import Member


@admin.register(Member)
class MemberAdmin(ModelAdmin):
    list_display = ["name", "section", "praise_team"]
    list_filter = ["section", "praise_team"]
    search_fields = ["name", "email"]
