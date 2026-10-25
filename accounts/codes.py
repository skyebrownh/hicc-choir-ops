"""Issue and check sign-in codes (AC-1, AC-2). Plain functions, called from the views."""

import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from accounts.models import SignInCode

CODE_LIFETIME = timedelta(minutes=10)  # AC-2
MAX_ATTEMPTS = 5  # AC-2

# verify_code results
OK, WRONG, EXPIRED, LOCKED = "ok", "wrong", "expired", "locked"


def issue_code(account):
    """Make a new code, store it hashed, and email it. A new code replaces older ones.

    If sending fails, the stored code is deleted and the error is raised.
    """
    code = f"{secrets.randbelow(1_000_000):06d}"
    SignInCode.objects.filter(account=account).delete()
    stored = SignInCode.objects.create(
        account=account,
        code=make_password(code),  # AC-1: never stored in plain text
        expires_at=timezone.now() + CODE_LIFETIME,
    )
    try:
        message = EmailMultiAlternatives(
            "Your HICC Choir Ops sign-in code",
            # AC-1: the plain-text version is the fallback for mail apps that don't show HTML.
            f"Your sign-in code is {code}. It works for 10 minutes.\n\n"
            "If you didn't ask for this, ignore this email.",
            None,  # None means the default from address
            [account.email],
        )
        message.attach_alternative(render_to_string("accounts/signin_code_email.html", {"code": code}), "text/html")
        message.send()
    except Exception:
        stored.delete()
        raise


def verify_code(account, code):
    """Check a code for an account. Returns OK, WRONG, EXPIRED or LOCKED."""
    # The row is locked for the whole check, so parallel guesses take turns and the
    # 5-try limit (AC-2) can't be beaten by sending them all at once.
    with transaction.atomic():
        stored = SignInCode.objects.select_for_update().filter(account=account).order_by("-id").first()
        # AC-2: no code, or one already used up by wrong tries, is the same as locked.
        if stored is None or stored.attempts >= MAX_ATTEMPTS:
            return LOCKED
        if stored.expires_at <= timezone.now():
            return EXPIRED
        if check_password(code, stored.code):
            stored.delete()  # AC-2: works once
            return OK
        stored.attempts += 1
        stored.save(update_fields=["attempts"])
        return LOCKED if stored.attempts >= MAX_ATTEMPTS else WRONG
