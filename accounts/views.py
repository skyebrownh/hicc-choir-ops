import logging

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from accounts import codes
from accounts.forms import CodeForm, EmailForm
from accounts.models import Account

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


@login_required
def home(request):
    """Placeholder landing page; #5 replaces it with the role's real home page."""
    return render(request, "accounts/home.html")
