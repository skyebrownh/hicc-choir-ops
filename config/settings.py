"""Django settings, read entirely from environment variables.

There is one settings module, not separate local and production ones: the app has a
single production and no staging (SPEC.md, Decisions), so the environment alone
switches behaviour. `DEBUG=false ... check --deploy` checks the production setup.
"""

import os
from pathlib import Path

from config.env import allowed_hosts, env_bool, env_list, parse_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# Both are required: no default means a missing value crashes at startup, not at 2am.
SECRET_KEY = os.environ["SECRET_KEY"]
DATABASES = {"default": parse_database_url(os.environ.get("DATABASE_URL"))}

# Off unless explicitly "true", so forgetting to set it can never expose debug pages.
DEBUG = env_bool("DEBUG")

# healthcheck.railway.app is the hostname Railway's health check calls from.
ALLOWED_HOSTS = allowed_hosts(DEBUG, env_list("ALLOWED_HOSTS"))
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    # Listed first so its `createsuperuser` (email only, no password) beats Django's.
    "accounts",
    # Unfold must come before django.contrib.admin so its templates override the admin's.
    "unfold",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",  # Django's checks require it for ArrayField
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves static files straight from gunicorn; it must sit right after
    # SecurityMiddleware.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # AC-4: after authentication, because it needs to know who is signed in.
    "accounts.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# AC-1: accounts sign in by emailed code, so our Account replaces Django's user.
AUTH_USER_MODEL = "accounts.Account"
# AC-4: stay signed in for 90 days from sign-in. Django's default is a fixed lifetime
# (SESSION_SAVE_EVERY_REQUEST is off), so this is not extended by use.
SESSION_COOKIE_AGE = 90 * 24 * 60 * 60
LOGIN_URL = "/signin/"
LOGIN_REDIRECT_URL = "/"

# AC-7: how many reverse proxies sit in front of the app (Railway's is 1). The sign-in
# limit uses this to find the real visitor address in X-Forwarded-For; 0 ignores the header.
NUM_PROXIES = int(os.environ.get("NUM_PROXIES", "0"))

# AC-1: codes go out through Resend's HTTPS API (Railway Hobby blocks SMTP). Locally
# with no key they print to the server console instead. Only DEBUG allows that
# fallback: in production a missing key makes sending fail loudly, not silently.
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM_ADDRESS = os.environ.get("RESEND_FROM_ADDRESS", "")
if DEBUG and not RESEND_API_KEY:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    EMAIL_BACKEND = "accounts.email.ResendEmailBackend"
DEFAULT_FROM_EMAIL = RESEND_FROM_ADDRESS or "HICC Choir Ops <signin@localhost>"

WSGI_APPLICATION = "config.wsgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
# Dates and "this week" use US Eastern time (CLAUDE.md, Conventions).
TIME_ZONE = "America/New_York"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
# `static/` holds our own files (the built Tailwind CSS); `staticfiles/` is where
# `collectstatic` gathers everything for WhiteNoise at deploy time.
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Railway's health check calls over plain HTTP, so a redirect to HTTPS would fail it.
# Matched against the path without its leading slash. Set even in DEBUG so a test can
# prove it.
SECURE_REDIRECT_EXEMPT = [r"^health/$"]

if not DEBUG:
    # Production runs behind Railway's HTTPS proxy, which says so in this header.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 3600  # raise once the site is known to work over HTTPS
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
