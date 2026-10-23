"""Limits on how often sign-in codes can be requested (AC-7)."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from accounts.models import SignInRequest

# AC-7: at most this many codes per email address per rolling hour.
MAX_PER_EMAIL = 5
# AC-7: higher per IP address, because the whole choir may share one church wifi address.
MAX_PER_IP = 20
WINDOW = timedelta(hours=1)


def client_ip(request):
    """The visitor's address, for the per-IP limit.

    X-Forwarded-For is written by whoever sends the request, so it can only be
    trusted for the entries our own proxies added. Each proxy appends the address
    it saw to the END of the list, so with NUM_PROXIES proxies in front of us the
    real visitor is that many entries from the end. Anything earlier could be forged.
    With no proxy (0) we ignore the header entirely.
    """
    proxies = settings.NUM_PROXIES
    forwarded = [part.strip() for part in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if part.strip()]
    if proxies > 0 and len(forwarded) >= proxies:
        return forwarded[-proxies]
    return request.META["REMOTE_ADDR"]


def over_limit(email, ip):
    """True if this email or this IP has used up its requests in the last hour."""
    since = timezone.now() - WINDOW
    recent = SignInRequest.objects.filter(created_at__gt=since)
    return (
        recent.filter(email=email.lower()).count() >= MAX_PER_EMAIL
        or recent.filter(ip_address=ip).count() >= MAX_PER_IP
    )


def record(email, ip):
    """Remember an allowed request, and forget ones too old to count any more."""
    now = timezone.now()
    SignInRequest.objects.filter(created_at__lte=now - WINDOW).delete()
    # Passed explicitly (not left to the model default) so there is one clock to read.
    SignInRequest.objects.create(email=email.lower(), ip_address=ip, created_at=now)
