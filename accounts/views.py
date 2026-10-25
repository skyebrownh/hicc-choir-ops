import logging

from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from accounts import codes, ratelimit
from accounts.forms import AccountForm, CodeForm, EmailForm
from accounts.models import Account, Role
from accounts.permissions import role_required

logger = logging.getLogger(__name__)

SESSION_KEY = "signin_email"

# AC-2: each way a code can fail gets its own message.
CODE_MESSAGES = {
    codes.WRONG: "That code isn't right. Try again.",
    codes.EXPIRED: "That code has expired. Request a new one.",
    codes.LOCKED: "Too many tries. Request a new code.",
}


def request_code(request):
    """Step 1 (AC-1): ask for an email address and send it a code."""
    form = EmailForm(request.POST or None)
    error = None
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        ip = ratelimit.client_ip(request)
        if ratelimit.over_limit(email, ip):
            # AC-7: send nothing and store nothing. Refused requests aren't recorded.
            error = "Too many requests. Please try again later."
            return render(request, "accounts/request_code.html", {"form": form, "error": error}, status=429)
        # AC-7: record before the account lookup, so unknown emails count too.
        ratelimit.record(email, ip)
        account = Account.objects.filter(email__iexact=email).first()
        if account is None:
            # AC-3: say so, send nothing and store nothing.
            error = "There's no account for that email. Check the spelling, or ask the director."
        else:
            try:
                codes.issue_code(account)
            except Exception as exc:
                # Log the kind of failure only: never the code or the address.
                logger.error("Sending a sign-in code failed: %s", type(exc).__name__)
                error = "We couldn't send your code right now. Please try again in a minute."
            else:
                # In the session, not the URL, so the address stays out of history and logs.
                request.session[SESSION_KEY] = account.email
                return redirect("enter-code")
    return render(request, "accounts/request_code.html", {"form": form, "error": error})


def enter_code(request):
    """Step 2 (AC-1, AC-2): check the code and sign the person in."""
    email = request.session.get(SESSION_KEY)
    account = Account.objects.filter(email=email).first() if email else None
    if account is None:
        return redirect("request-code")

    form = CodeForm(request.POST or None)
    error = None
    if request.method == "POST" and form.is_valid():
        result = codes.verify_code(account, form.cleaned_data["code"])
        if result == codes.OK:
            del request.session[SESSION_KEY]
            login(request, account)
            return redirect("home")
        error = CODE_MESSAGES[result]
    return render(request, "accounts/enter_code.html", {"form": form, "error": error, "email": email})


@require_POST
def sign_out(request):
    """AC-4: end the session. POST only, so a stray link or prefetch can't sign anyone out."""
    logout(request)
    return redirect("request-code")


def home(request):
    """AC-4: the front door. Everyone lands on their own role's home page."""
    if request.user.is_admin:
        return redirect("week-ahead")
    return redirect("attendance-home")


@role_required(Role.ADMIN)
def week_ahead(request):
    """AC-4: admins' home page. A placeholder: later issues fill in the week's events."""
    return render(request, "accounts/week_ahead.html")


@role_required(Role.SECTION_LEADER)
def attendance_home(request):
    """AC-4: section leaders' home page. A placeholder: later issues add their sections' attendance."""
    return render(request, "accounts/attendance_home.html")


@role_required(Role.ADMIN)
def account_list(request):
    """AC-5: admins see every account: admins first, then leaders, each by name (or email when there's no member)."""
    accounts = Account.objects.select_related("member")
    accounts = sorted(accounts, key=lambda a: (not a.is_admin, a.display_name.lower()))
    return render(request, "accounts/account_list.html", {"accounts": accounts})


@role_required(Role.ADMIN)
def account_add(request):
    """AC-5, AC-6: admins give a member an account, or make an admin with no member."""
    form = AccountForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("account-list")
    return render(request, "accounts/account_form.html", {"form": form, "title": "Add an account"})
