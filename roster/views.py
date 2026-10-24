from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import Role
from accounts.permissions import role_required
from roster.forms import MemberForm, StatusChangeForm
from roster.models import Member, Status, StatusChange


def member_list(request):
    """RO-3: admins see everyone, section leaders their own sections."""
    members = Member.objects.visible_to(request.user).order_by("name")
    return render(request, "roster/member_list.html", {"members": members})


def member_detail(request, pk):
    """RO-3: a member outside the leader's sections is "not found"."""
    member = get_object_or_404(Member.objects.visible_to(request.user), pk=pk)
    # RO-2: the status history, newest first.
    return render(request, "roster/member_detail.html", {"member": member, "history": list(member.status_history())})


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
        # RO-2: the member and their first status are saved together or not at all.
        with transaction.atomic():
            member = form.save()
            StatusChange.objects.create(
                member=member, status=form.cleaned_data["initial_status"] or Status.ACTIVE,
                effective_on=timezone.localdate(),
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


@role_required(Role.ADMIN)
def member_status(request, pk):
    """RO-2, RO-3: admins record a status change. Past changes are never edited here (fix them in the Django admin)."""
    member = get_object_or_404(Member.objects.visible_to(request.user), pk=pk)
    # The member is set up front so the model's "must change" check (RO-2) can see their history.
    form = StatusChangeForm(request.POST or None, instance=StatusChange(member=member))
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("member-detail", pk=member.pk)
    return render(
        request,
        "roster/status_form.html",
        {"form": form, "member": member, "title": f"Change status for {member.name}"},
    )
