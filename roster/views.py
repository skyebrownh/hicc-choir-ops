from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import Role
from accounts.permissions import role_required
from roster.forms import MemberForm
from roster.models import Member


def member_detail(request, pk):
    member = get_object_or_404(Member, pk=pk)
    return render(request, "roster/member_detail.html", {"member": member})


@role_required(Role.ADMIN)
def member_add(request):
    """RO-3: admins add members."""
    form = MemberForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        member = form.save()
        return redirect("member-detail", pk=member.pk)
    return render(request, "roster/member_form.html", {"form": form, "title": "Add a member"})
