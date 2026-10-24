from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import Role, Section
from accounts.permissions import role_required
from roster.forms import MemberForm, PraiseTeamChangeForm, SectionChangeForm, StatusChangeForm
from roster.models import Member, PraiseTeamChange, SectionChange, Status, StatusChange


def member_list(request):
    """RO-3, RO-6: admins see everyone, section leaders their own sections. Members sit under the section they are in now."""
    members = Member.objects.visible_to(request.user).with_current_status()
    # RO-2: in each section, Active first, then On Break, then Inactive, then by name.
    # Rank follows the order the statuses are declared in `Status` (Active, On Break, Inactive).
    status_rank = {status: rank for rank, status in enumerate(Status.values)}
    members = sorted(members, key=lambda m: (status_rank.get(m.status_now, len(status_rank)), m.name.lower()))
    for member in members:
        member.status_label = Status(member.status_now).label if member.status_now else ""
    # Sections in the choir's usual order (SPEC.md lists them Soprano, Alto, Tenor, Bass).
    groups = [
        {"label": section.label, "members": [m for m in members if m.section_now == section.value]}
        for section in Section
    ]
    return render(
        request,
        "roster/member_list.html",
        {"groups": [g for g in groups if g["members"]], "has_members": bool(members)},
    )


def member_detail(request, pk):
    """RO-3: a member outside the leader's sections is "not found"."""
    member = get_object_or_404(Member.objects.visible_to(request.user), pk=pk)
    # RO-2, RO-6: each history is read once, newest first; the page takes the current value and the one before from it.
    return render(
        request,
        "roster/member_detail.html",
        {
            "member": member,
            "history": list(member.status_history()),
            "section_history": list(member.section_history()),
            "praise_team_history": list(member.praise_team_history()),
        },
    )


def member_history(request, pk):
    """RO-6, RO-3: the section and Praise Team histories together. Same visibility as the member's own page."""
    member = get_object_or_404(Member.objects.visible_to(request.user), pk=pk)
    return render(
        request,
        "roster/member_history.html",
        {
            "member": member,
            "section_history": member.section_history(),
            "praise_team_history": member.praise_team_history(),
        },
    )


def member_status_history(request, pk):
    """RO-2, RO-3: the full list of status changes. Same visibility as the member's own page."""
    member = get_object_or_404(Member.objects.visible_to(request.user), pk=pk)
    return render(
        request, "roster/status_history.html", {"member": member, "history": member.status_history()}
    )


@role_required(Role.ADMIN)
def member_add(request):
    """RO-3: admins add members."""
    form = MemberForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        # RO-2, RO-6: the member and their first status, section and Praise Team flag are saved together
        # or not at all. Every member gets a first row of each, so their history is complete.
        with transaction.atomic():
            member = form.save()
            today = timezone.localdate()
            StatusChange.objects.create(
                member=member, status=form.cleaned_data["initial_status"] or Status.ACTIVE, effective_on=today
            )
            SectionChange.objects.create(member=member, section=form.cleaned_data["initial_section"], effective_on=today)
            PraiseTeamChange.objects.create(
                member=member, praise_team=form.cleaned_data["initial_praise_team"], effective_on=today
            )
        return redirect("member-detail", pk=member.pk)
    return render(request, "roster/member_form.html", {"form": form, "title": "Add a member"})


@role_required(Role.ADMIN)
def member_edit(request, pk):
    """RO-3: admins edit members."""
    member = get_object_or_404(Member.objects.visible_to(request.user), pk=pk)
    form = MemberForm(request.POST or None, instance=member)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("member-detail", pk=member.pk)
    return render(request, "roster/member_form.html", {"form": form, "member": member, "title": f"Edit {member.name}"})


def _record_change(request, pk, form_class, change_model, template, title, current):
    """RO-2, RO-6, RO-3: the page admins use to record one change. Past changes are never edited here (fix them in the Django admin)."""
    member = get_object_or_404(Member.objects.visible_to(request.user), pk=pk)
    # The member is set up front so the model's "must change" check can see their history.
    form = form_class(request.POST or None, instance=change_model(member=member))
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("member-detail", pk=member.pk)
    return render(
        request,
        template,
        {"form": form, "member": member, "title": title.format(member.name), "current": current(member)},
    )


@role_required(Role.ADMIN)
def member_status(request, pk):
    """RO-2, RO-3: admins record a status change."""
    return _record_change(
        request, pk, StatusChangeForm, StatusChange, "roster/status_form.html",
        "Change status for {}", lambda m: m.current_status_display or "not set",
    )


@role_required(Role.ADMIN)
def member_section(request, pk):
    """RO-6, RO-3: admins record a section change."""
    return _record_change(
        request, pk, SectionChangeForm, SectionChange, "roster/change_form.html",
        "Change section for {}", lambda m: m.current_section_display or "not set",
    )


@role_required(Role.ADMIN)
def member_praise_team(request, pk):
    """RO-6, RO-3: admins record joining or leaving the Praise Team."""
    return _record_change(
        request, pk, PraiseTeamChangeForm, PraiseTeamChange, "roster/change_form.html",
        "Change Praise Team for {}", lambda m: "on the Praise Team" if m.current_praise_team else "not on the Praise Team",
    )
