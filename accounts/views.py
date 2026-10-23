import logging

from django.contrib.auth import login
from django.shortcuts import redirect, render

from accounts import codes
from accounts.forms import CodeForm, EmailForm
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


def home(request):
    """AC-4: the front door. Everyone lands on their own role's home page."""
    if request.user.is_admin:
        return redirect("week-ahead")
    return redirect("attendance-home")


@role_required(Role.ADMIN)
def week_ahead(request):
    """Admins' home page. A placeholder: later issues fill in the week's events."""
    return render(request, "accounts/week_ahead.html")


@role_required(Role.SECTION_LEADER)
def attendance_home(request):
    """Section leaders' home page. A placeholder: later issues add their sections' attendance."""
    return render(request, "accounts/attendance_home.html")
