# HICC Choir Ops

Roster, attendance and weekly song-set planning for the HICC choir.

## What it does

Section leaders mark attendance on their phones and see who needs a follow-up. The choir director plans each week's set with every song's history, leads and stats in front of her. The full spec is in [SPEC.md](SPEC.md).

## Getting started

### Prerequisites

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)
- Postgres (a local database for development)
- Tailwind's standalone CLI (a single binary, no Node needed)

### Install

```sh
uv sync                      # installs Python packages from uv.lock
cp .env.example .env         # then edit .env (see the comments inside)
createdb hicc_choir_ops      # the local Postgres database named in .env.example
uv run --env-file .env python manage.py migrate
```

Get Tailwind's standalone CLI (Apple Silicon Mac shown; pick your platform's file from the [releases page](https://github.com/tailwindlabs/tailwindcss/releases/tag/v4.3.3)). It lives in `bin/`, which git ignores:

```sh
mkdir -p bin
curl -sL -o bin/tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/download/v4.3.3/tailwindcss-macos-arm64
chmod +x bin/tailwindcss
```

### Run

```sh
uv run --env-file .env python manage.py runserver
```

Open http://127.0.0.1:8000/health/ (shows `ok`), http://127.0.0.1:8000/health/db/ (`ok` when Postgres answers) and http://127.0.0.1:8000/admin/ (the Unfold login). Create a local admin with `uv run --env-file .env python manage.py createsuperuser` (it asks for an email only: there are no passwords), then sign in at http://127.0.0.1:8000/signin/. With no `RESEND_API_KEY` set, the 6-digit code prints in the terminal running the server.

Accounts replaced Django's built-in user (issue #4). A database migrated before that has to be reset once: `dropdb hicc_choir_ops && createdb hicc_choir_ops`, then `migrate` and `createsuperuser` again.

After changing templates or `tailwind/input.css`, rebuild the CSS and commit `static/app.css`:

```sh
bin/tailwindcss -i tailwind/input.css -o static/app.css --minify
```

### Test

```sh
uv run --env-file .env python manage.py test
DEBUG=false uv run --env-file .env python manage.py check --deploy
```

## Deploy

The app runs on Railway (Hobby plan), deployed from GitHub, in the existing heritage-media project: one service for this repo plus its own Postgres. There is no staging copy (SPEC.md, Decisions).

1. In the Railway project, add a Postgres database, then a service from this GitHub repo.
2. Set these variables on the service:

   | Variable | Value |
   | --- | --- |
   | `SECRET_KEY` | a new long random string |
   | `DATABASE_URL` | reference the Postgres service's `DATABASE_URL` |
   | `ALLOWED_HOSTS` | the service's address, e.g. `your-app.up.railway.app` (`healthcheck.railway.app` is built in) |
   | `CSRF_TRUSTED_ORIGINS` | `https://` plus the same address |
   | `RESEND_API_KEY` | a Resend API key with sending access to the sending subdomain |
   | `RESEND_FROM_ADDRESS` | e.g. `HICC Choir Ops <signin@mail.hicctools.com>` (on the domain verified in Resend) |
   | `NUM_PROXIES` | `1`: Railway's proxy sits in front of the app, so the sign-in limit (AC-7) reads the visitor's address from the end of `X-Forwarded-For` |

   Leave `DEBUG` unset: production runs with it off.
3. In the service's Settings, set:
   - **Pre-deploy command:** `python manage.py migrate --noinput` (if it fails, the previous version keeps running)
   - **Start command:** `python manage.py migrate --check && python manage.py collectstatic --noinput && gunicorn config.wsgi` (`migrate --check` refuses to start if a migration is missing; `collectstatic` gathers the admin's styles and `static/app.css` for WhiteNoise; gunicorn's settings are in `gunicorn.conf.py`)
   - **Healthcheck path:** `/health/`
4. Generate a public domain, deploy, and check the deploy log shows the health check passing. Then `/health/db/` should show `ok` and `/admin/` should load over HTTPS.

After the first deploy, check the sign-in limit sees real visitor addresses. Request a code from a phone on mobile data, then in `railway run python manage.py shell` run `from accounts.models import SignInRequest; print(SignInRequest.objects.latest("created_at").ip_address)`. It should be the phone's public address, not a Railway internal one (10.x.x.x or 100.x.x.x). If not, set `NUM_PROXIES` to `2`: no code change needed.

### One-time database reset (issue #4)

The accounts app replaces Django's user model, which can't be swapped once migrations have run. Before the first deploy that includes it, reset the production database (this deletes its data: only the admin login exists so far), then after the deploy create the admin with `railway run python manage.py createsuperuser`.

## How work happens

Every change starts from a GitHub issue; [CLAUDE.md](CLAUDE.md) has the project's conventions.
