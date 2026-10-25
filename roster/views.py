from itertools import groupby

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateformat import format as format_date
from django.views.decorators.http import require_POST

from accounts.models import Role, Section
from accounts.permissions import role_required
from roster.events import created_message, create_upcoming_events
from roster.forms import EventEditForm, EventForm, MemberFilterForm, MemberForm, PraiseTeamChangeForm, SectionChangeForm, StatusChangeForm
from roster.models import Event, Member, PraiseTeamChange, SectionChange, Status, StatusChange, date_format


def member_list(request):
    """RO-3, RO-6: admins see everyone, section leaders their own sections. Members sit under the section they are in now."""
    members = Member.objects.visible_to(request.user).with_current_status()
    # RO-4: any filter key in the URL is the whole chosen view (keys it leaves out mean "default") and is
    # remembered; a URL with none (the Members link, Back, Cancel) uses what was remembered. Reset is a link
    # with every key empty, which remembers "all defaults". The raw values are saved and re-validated on
    # each read, so a section the leader has since lost is dropped like any invalid value.
    # Signing out clears them too: logout() flushes the whole session.
    if any(name in request.GET for name in MemberFilterForm.FIELD_NAMES):
        chosen = {name: request.GET.get(name, "") for name in MemberFilterForm.FIELD_NAMES}
        # Only write when it changed, so re-opening the same filtered link doesn't save the session again.
        if request.session.get("member_filters") != chosen:
            request.session["member_filters"] = chosen
    else:
        chosen = request.session.get("member_filters", {})
    # RO-4: narrow by those filters, before sorting and grouping.
    filters = MemberFilterForm(chosen, request.user)
    members = filters.filter(members)
    # RO-2: in each section, Active first, then On Break, then Inactive; within a status, Praise Team
    # members (their current flag) before the others, then by name. `not flag` is the sort key because
    # False sorts before True, so members on the team come first; no flag at all counts as not on it.
    # Rank follows the order the statuses are declared in `Status` (Active, On Break, Inactive).
    status_rank = {status: rank for rank, status in enumerate(Status.values)}
    members = sorted(
        members,
        key=lambda m: (status_rank.get(m.status_now, len(status_rank)), not m.praise_team_now, m.name.lower()),
    )
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
        {"groups": [g for g in groups if g["members"]], "has_members": bool(members), "filters": filters},
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
            member.start_history(
                status=form.cleaned_data["initial_status"] or Status.ACTIVE,
                section=form.cleaned_data["initial_section"],
                praise_team=form.cleaned_data["initial_praise_team"],
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


def _by_month(events):
    """AT-1, AT-3: [("November 2026", [events...]), ...], one group per month, in the order the events came in."""
    first_of_month = lambda event: event.date.replace(day=1)
    return [(format_date(month, "F Y"), list(group)) for month, group in groupby(events, key=first_of_month)]


@role_required(Role.ADMIN)
def event_list(request):
    """AT-1, AT-3: events from today on, in date order. Canceled ones stay in place, badged."""
    events = Event.objects.filter(date__gte=timezone.localdate())
    return render(request, "roster/event_list.html", {"months": _by_month(events)})


@role_required(Role.ADMIN)
def event_past(request):
    """AT-3: events before today, newest first, canceled ones included. Read-only."""
    events = Event.objects.filter(date__lt=timezone.localdate()).order_by("-date", "-id")
    return render(request, "roster/event_past.html", {"months": _by_month(events)})


@role_required(Role.ADMIN)
def event_restore(request, pk):
    """AT-3: undoes a cancel, for an event dated today or later that is canceled. Anything else is "not found".

    Same limit as canceling: a past event already counted in rates and flags is fixed in the Django admin.
    """
    event = get_object_or_404(Event, pk=pk, canceled=True, date__gte=timezone.localdate())
    if request.method == "POST":
        event.canceled = False
        event.save(update_fields=["canceled"])
        messages.success(request, f"{event.title} on {date_format(event.date)} is back on.")
        return redirect("event-list")
    return render(request, "roster/event_confirm_restore.html", {"event": event})


@role_required(Role.ADMIN)
@require_POST
def events_create_upcoming(request):
    """AT-1: the button that does what the scheduled command does, and says how many events were new."""
    count = create_upcoming_events()
    messages.success(request, created_message(count))
    return redirect("event-list")


@role_required(Role.ADMIN)
def event_add(request):
    """AT-2: admins add a special event or extra rehearsal, on any date. Several can share a date."""
    form = EventForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("event-list")
    return render(request, "roster/event_form.html", {"form": form, "title": "Add an event"})


@role_required(Role.ADMIN)
def event_edit(request, pk):
    """AT-2: admins change an upcoming event's name, who is expected and notes (canceled ones too).

    Only today or later: who was expected at a past event feeds rates and flags, so it isn't edited here
    (fix it in the Django admin).
    """
    event = get_object_or_404(Event, pk=pk, date__gte=timezone.localdate())
    form = EventEditForm(request.POST or None, instance=event)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{event.title} on {date_format(event.date)} is updated.")
        return redirect("event-list")
    return render(request, "roster/event_form.html", {"form": form, "event": event, "title": "Edit event"})


@role_required(Role.ADMIN)
def event_cancel(request, pk):
    """AT-3: asks first, then cancels. Only an event dated today or later that is not canceled already.

    Anything else is "not found", so a direct POST can't cancel history that rates and flags rely on.
    """
    event = get_object_or_404(Event, pk=pk, canceled=False, date__gte=timezone.localdate())
    if request.method == "POST":
        event.canceled = True
        event.save(update_fields=["canceled"])
        messages.success(request, f"{event.title} on {date_format(event.date)} is canceled.")
        return redirect("event-list")
    return render(request, "roster/event_confirm_cancel.html", {"event": event})
