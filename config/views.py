from django.db import OperationalError, connection
from django.http import HttpResponse


def health(request):
    """Railway's health check. No login, so it must never show data.

    It deliberately skips the database: it answers "is the process up", nothing more.
    If it failed whenever the database blipped, Railway would restart a healthy app.
    """
    return HttpResponse("ok", content_type="text/plain")


def health_db(request):
    """Confirms the database answers. For Skye or an uptime monitor; Railway doesn't use it."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except OperationalError:
        return HttpResponse("database unavailable", content_type="text/plain", status=503)
    return HttpResponse("ok", content_type="text/plain")
