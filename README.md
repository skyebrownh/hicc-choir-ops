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

To reset your local database to a known state with fake members, run `uv run --env-file .env python manage.py seed basic`. It deletes all members and all section-leader accounts (admin accounts are kept), and refuses to run unless `DEBUG=true`. The `basic` scenario also creates two fake leaders to sign in as: `alto.leader@example.com` (Alto) and `tenor.leader@example.com` (Tenor and Bass); their codes print in the server console. One member is On Break (Beth Rowe) and one is Inactive (Ian Stone), so the roster's status filter has something to find. Two members have a little history to look at: Tim Hayes moved from Alto to Tenor 30 days ago, and Amy Walker joined the Praise Team 30 days ago (and has a break behind her).

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

To run a command in production, use `railway ssh --service hicc-choir-ops -- "<command>"`, which runs inside the service (the example below shows how to quote a command that itself contains quotes). `railway run` doesn't work for this: it runs on your Mac, which can't reach the database on Railway's internal network.

After the first deploy, check the sign-in limit sees real visitor addresses. Request a code from a phone on mobile data, then run this to show the three newest requests:

```sh
railway ssh --service hicc-choir-ops -- "python manage.py shell -c 'from accounts.models import SignInRequest as S; print(list(S.objects.order_by(\"-created_at\").values_list(\"ip_address\",\"created_at\")[:3]))'"
```

The first address in the list is the newest, and it should be the phone's public address, not a Railway internal one (10.x.x.x or 100.x.x.x). If not, set `NUM_PROXIES` to `2`: no code change needed.

### One-time database reset (issue #4)

The accounts app replaces Django's user model, which can't be swapped once migrations have run. Before the first deploy that includes it, reset the production database (this deletes its data: only the admin login exists so far), then after the deploy create the admin with `railway ssh --service hicc-choir-ops -- "python manage.py createsuperuser"` (it asks its questions in your terminal).

## Scheduled jobs

Events for the current week and the next 4 are created by `python manage.py create_events` (AT-1). It is safe to rerun, and admins can also press **Create upcoming events** on the Events page. Railway runs it every day as a second service, because the app's own service can't run on a schedule:

1. In the Railway project, add a service from this same GitHub repo, and name it e.g. `hicc-choir-ops-events`.
2. Give it the same variables as the app service (at least `SECRET_KEY` and `DATABASE_URL`), by referencing the app service's variables.
3. In its Settings, set the **Start command** to `python manage.py create_events` and the **Cron schedule** to `0 9 * * *`. Railway schedules in UTC, so this is 4 or 5 in the morning US Eastern. Leave the **Healthcheck path** and **Pre-deploy command** empty: the service runs, exits, and waits for the next day.
4. Check the first run in the service's deploy log: it should say `Created N events.`

## Backups

Railway's Hobby plan has no database backups, so Skye's Mac makes them (#19). Every day, a scheduled job runs `pg_dump` inside production's Postgres service (`Postgres-KuxJ`) through the Railway CLI and saves a compressed copy in `~/Backups/hicc-choir-ops/`, keeping the newest 30. No database password is stored anywhere; it uses the Railway CLI's own login.

The backups hold real member names and emails, so they stay on the Mac (in a folder only Skye's account can open) and are never committed. Railway-side or off-Mac copies are not set up.

### Setting it up

Prerequisites: the [Railway CLI](https://docs.railway.com/guides/cli), logged in (`railway login`) and linked to this project (`railway link`).

```sh
bash backup/install.sh
```

This copies `backup/backup.sh` into the backup folder and installs a `launchd` job (macOS's scheduler) that checks at 10am every day and at login. It only makes a backup when none exists yet for today's date (US Eastern), so a day missed while the Mac was off is caught up when it is next on. Rerun the installer after changing `backup/backup.sh`. To stop the job (backups are kept): `bash backup/install.sh --uninstall`.

### Day to day

| Task | Command |
| --- | --- |
| See how backups are doing | `~/Backups/hicc-choir-ops/backup.sh status` |
| Back up right now | `~/Backups/hicc-choir-ops/backup.sh now` |
| Back up only if today has none | `~/Backups/hicc-choir-ops/backup.sh run` |

- **A banner, "HICC backup saved"**, once a day means it worked.
- **An alert, "HICC backup failed"**, stays on screen until dismissed. It says what went wrong and how old the newest good backup is. The most common cause is an expired Railway login: run `railway login`, then `backup.sh now`. Railway's own messages from the latest attempt are in `last-run-output.log` in the backup folder.
- `backup.log` has one line per attempt (file names and sizes only, never data); "Checked … nothing to do" lines show the job is running.
- macOS shows the notifications as coming from "Script Editor". If they don't appear, allow Script Editor in System Settings → Notifications.
- To test the failure alert without touching anything: `RAILWAY_PROJECT_ID=00000000-0000-0000-0000-000000000000 ~/Backups/hicc-choir-ops/backup.sh now`

### Practice restore

Do this now and then to make sure the backups really work. It restores into a throwaway database on your everyday local Postgres, never production.

```sh
# Make an empty database
createdb hicc_restore_test

# Load the newest backup (ON_ERROR_STOP stops at the first error instead of carrying on)
F=$(ls ~/Backups/hicc-choir-ops/hicc-*.sql.gz | sort | tail -1)
gunzip -c "$F" | psql -d hicc_restore_test -v ON_ERROR_STOP=1 -q -o /dev/null

# Count accounts in the copy, then in production (read-only); they should match
psql -d hicc_restore_test -At -c "select count(*) from accounts_account"
railway ssh --service Postgres-KuxJ --environment production -- psql -At -c "select count(*) from accounts_account"

# Clean up
dropdb hicc_restore_test
```

The table name is Django's `<app>_<model>`; if the count query says the table doesn't exist, run `psql -d hicc_restore_test -c '\dt'` to list the tables. Counts can differ slightly if something changed since the backup was made.

Last tested: not yet tested. After the first practice restore, put the date and what matched here.

### Emergency restore into Railway

Only if production's data is lost or damaged, and only after talking it through first. The outline: make a fresh backup of what's there now with `backup.sh now`, empty or replace production's database, then load the chosen backup with Railway's own `psql`:

```sh
gunzip -c ~/Backups/hicc-choir-ops/hicc-YYYY-MM-DD-HHMM.sql.gz \
  | railway ssh --service Postgres-KuxJ --environment production -- psql -v ON_ERROR_STOP=1
```

Then check `/health/db/` shows `ok` and sign in to confirm the data looks right.

## Importing members

A one-time command loads the existing member list from a CSV file (RO-5). The real list never goes into git: keep it in `private-data/`, which is git-ignored. Git doesn't track empty folders, so make it yourself once:

```sh
mkdir -p private-data
```

Convert the assistant's plain-text list to a CSV by hand, with a header row and these columns (only `name` and `section` are required):

| Column | What goes in it |
| --- | --- |
| `name` | The member's full name |
| `section` | Soprano, Alto, Tenor or Bass (any capitals) |
| `praise_team` | `yes`, `y`, `true` or `1` for the Praise Team; `no`, `n`, `false`, `0` or blank for not |
| `phone`, `email`, `notes` | Optional |

Then run it with the file's path:

```sh
uv run --env-file .env python manage.py import_members private-data/members.csv
```

Every member is added as Active, with their section and Praise Team flag, all dated today. The command checks every row first: if any row is bad it imports nothing and lists each problem as `line N: reason` (never the person's details), so fix the file and run it again. A name already on the roster counts as a bad row, so a second run can't create duplicates.

### Importing in production

The real list is imported once, into production's database. Two things make it different from running it locally. The CSV is on your Mac but the command has to run inside Railway's service (see Deploy, "To run a command in production", above), so the file is piped in from your Mac. And it writes real data, so take a backup first.

1. Check the file works first: run the command locally against `seed basic` data (see Getting started; `seed` resets your local members, so only do this on fake data). Use names that aren't in the seed data, or the rows will be reported as already on the roster. A bad row in production just stops the import with nothing added, but finding it locally is quicker.
2. Make a fresh backup, so there is a copy from just before the import: `~/Backups/hicc-choir-ops/backup.sh now`
3. Send the file and run the import, from the project folder (so the path to the CSV is right). `cat` feeds the CSV into `railway ssh` as input (the same way the restore above feeds in a backup), and `/dev/stdin` tells the command to read its file from that input. The command writes no copy of the file, and the member details are not part of the command line, so they are not in your shell history either. Whether Railway keeps any record of what passes through an ssh session hasn't been checked:

   ```sh
   cat private-data/members.csv | railway ssh --service hicc-choir-ops --environment production -- python manage.py import_members /dev/stdin
   ```
4. Read the output. "Imported N members." means it worked. Anything else means nothing was imported: either `line N: reason` problems (a name that appears twice in the file, even in different capitals, is also a bad row), or a problem with the whole file ("The file needs a header row...", or text that isn't UTF-8). Fix `private-data/members.csv` and run step 3 again. If it just sits there with no output, press Ctrl-C and check the Members list before trying again: the import is all-or-nothing, so you will see either all the members or none.
5. Sign in to the production site and check the Members list: the count and a few names, sections and Praise Team flags should match the file. Each member should be Active, dated the day you imported.
6. Don't run it a second time once it has worked: every name would be reported as already on the roster. To add someone later, use the Add member page. Keep `private-data/members.csv` only on your Mac (it is git-ignored), or delete it once you no longer need it.

This was done once for the real choir list on 2026-10-25, and step 3 worked as written: `railway ssh` passed the piped file through. The import is a one-time job, so there is normally no reason to run it again.

## How work happens

Every change starts from a GitHub issue; [CLAUDE.md](CLAUDE.md) has the project's conventions.
