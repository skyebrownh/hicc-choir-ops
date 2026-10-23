from django.conf import settings
from django.contrib.auth.views import redirect_to_login

# Pages a signed-out visitor may open: the health checks Railway calls, the sign-in
# pages themselves, and the admin's login URL (which redirects to ours).
# Prefixes, so "/static/" covers every file under it.
PUBLIC_PREFIXES = (
    "/health/",
    "/signin/",
    "/static/",
    "/admin/login/",
)


class LoginRequiredMiddleware:
    """AC-4: send signed-out visitors to sign-in from every page except PUBLIC_PREFIXES.

    Protecting by default means a page added later is private until someone
    deliberately lists it above, rather than public until someone remembers a decorator.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated and not request.path.startswith(PUBLIC_PREFIXES):
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
        return self.get_response(request)
