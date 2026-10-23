"""Limits on how often sign-in codes can be requested (AC-7)."""

from datetime import timedelta

from django.utils import timezone

from accounts.models import SignInRequest

# AC-7: at most this many codes per email address per rolling hour.
MAX_PER_EMAIL = 5
# AC-7: higher per IP address, because the whole choir may share one church wifi address.
MAX_PER_IP = 20
WINDOW = timedelta(hours=1)


def client_ip(request):
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
