# CLAUDE.md

## HICC Choir Ops

A web app for the HICC choir's director, her assistant and section leaders: roster, attendance and weekly song-set planning. **SPEC.md is the source of truth** for what it does and why. **GitHub issues** hold the work.

@SPEC.md

## Stack (do not change without asking)

- Python 3.12+, managed with uv (see Commands)
- Django, current stable, with server-rendered templates (no React, Vue or other SPA framework)
- Tailwind CSS, pre-built with Tailwind's standalone CLI (no Node or npm). The built CSS is committed and served by WhiteNoise; never edit it by hand.
- Small vanilla JavaScript where needed (slot picking, copy to clipboard)
- Postgres everywhere, through `DATABASE_URL`: a local Postgres for development, Railway Postgres in production
- Hosting: Railway Hobby plan, deployed from GitHub. gunicorn serves the app; WhiteNoise serves static files.
- Sign-in email: Resend's HTTPS API (Railway Hobby blocks SMTP)
- Django's built-in test runner
- Approved packages: `django`, `psycopg[binary]`, `gunicorn`, `whitenoise`, `django-unfold`. Anything else (including a Resend client library) needs approval first.

## Architecture

Three Django apps (modules): **accounts** (sign-in, roles), **roster** (members, status, section and Praise Team history, events, attendance, rates) and **songs** (songs, sets, stats, history import). Songs may depend on roster for leads; roster never depends on songs.

The Django project package is `config/` (settings, URLs, the health-check views); `accounts`, `roster` and `songs` are added by their issues. Settings are read from environment variables (`SECRET_KEY` and `DATABASE_URL` are required; `DEBUG` is off unless `true`). There is one settings module and no staging (SPEC.md, Decisions): the environment alone switches behaviour.

Railway: the pre-deploy command, start command and health check path (`/health/`) are set in the Railway dashboard, not in a `railway.json`. README's Deploy section lists them.

## Conventions

- Code comments cite the requirement ID they implement (e.g. `# AT-7: past, expected, unmarked means Absent`).
- Check the user's role on the server for every page and action. A section leader who asks for something they can't see gets "not found", not "forbidden" (see SPEC.md's Business rules).
- Dates and "this week" use US Eastern time.
- Personal data (member lists, text exports, history CSVs) never goes into git or logs. It lives in a git-ignored folder.
- Tests follow SPEC.md's Testing approach: Django's test client, signed in as a specific role, and every requirement ID has a test that names it.

## Commands

- Run locally: `uv run --env-file .env python manage.py runserver` (copy `.env.example` to `.env` first)
- Run tests: `uv run --env-file .env python manage.py test`
- Deploy check: `DEBUG=false uv run --env-file .env python manage.py check --deploy`
- Rebuild the CSS after changing templates or `tailwind/input.css`: `bin/tailwindcss -i tailwind/input.css -o static/app.css --minify` (the binary is git-ignored; README says how to get it). Commit the rebuilt `static/app.css`.

Project facts for Skye's personal skills (checks, merge style, whether merging deploys) are in `.claude/workflow.md`; update it with `/setup-project`.
