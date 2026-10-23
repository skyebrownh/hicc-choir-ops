from functools import wraps

from django.http import Http404


def role_required(*roles):
    """Show a page only to accounts with one of `roles`; everyone else gets "not found".

    "Not found", not "forbidden", so a section leader typing a URL they may not see
    can't tell whether the page exists (SPEC.md, Business rules). Sign-in itself is
    already enforced for every page by LoginRequiredMiddleware.
    """

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.user.role not in roles:
                raise Http404
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
