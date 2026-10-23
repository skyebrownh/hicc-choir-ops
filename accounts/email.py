"""Email backend that sends through Resend's HTTPS API, using only the standard library."""

import json
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

RESEND_URL = "https://api.resend.com/emails"


class ResendEmailBackend(BaseEmailBackend):
    """Django calls `send_messages`; we POST each message to Resend. Any failure raises."""

    def send_messages(self, email_messages):
        if not settings.RESEND_API_KEY:
            # Fail loudly: a silent no-send would leave people waiting for a code.
            raise RuntimeError("RESEND_API_KEY is not set")
        sent = 0
        for message in email_messages:
            payload = {
                "from": message.from_email,
                "to": message.to,
                "subject": message.subject,
                "text": message.body,
            }
            request = urllib.request.Request(
                RESEND_URL,
                data=json.dumps(payload).encode(),
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    "Content-Type": "application/json",
                    # Resend rejects requests that have no User-Agent.
                    "User-Agent": "hicc-choir-ops",
                },
                method="POST",
            )
            # Raises HTTPError/URLError on a failed or refused send.
            with urllib.request.urlopen(request, timeout=10):
                pass
            sent += 1
        return sent
