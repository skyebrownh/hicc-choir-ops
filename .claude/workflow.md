# Workflow facts

<!--
Facts about this project that Skye's personal skills (/handover, /ship, /merge) read,
so the skills themselves stay the same in every project. Written by
/setup-project; edit by hand any time. Keep each section's heading exactly as
it is: the skills find facts by heading.
-->

## Process version

<!-- Which version of Skye's process this project is set up for. Change it only through /setup-project, which applies the migrations that bring a project up to date. -->

3

## Default branch

`main`

## Checks before committing

<!-- Every command must pass before each commit during the build, and again when /ship runs. One per line. -->

```sh
uv run --env-file .env python manage.py test
DEBUG=false uv run --env-file .env python manage.py check --deploy
```

## Manual test setup

<!-- What Skye does before trying a change by hand, and anything to undo afterwards. /handover starts its manual test steps from here. -->

- apply database migrations first (a new migration otherwise breaks the seed and the pages): `uv run --env-file .env python manage.py migrate`
- reset local data: `uv run --env-file .env python manage.py seed <scenario>` (the handover names the scenario; admin logins are kept)
- start the dev server: `uv run --env-file .env python manage.py runserver`, then open http://127.0.0.1:8000/
- for admin changes, log in at http://127.0.0.1:8000/admin/ with your local superuser

## Pull requests

- Template: `.github/pull_request_template.md`
- Copy the issue's milestone and labels onto the PR: yes

## Merging

- Single-issue PR: squash, subject `<issue title> (#<PR>)`
- Parent PR: rebase
- Merging deploys: yes
- Where it deploys: Railway production, from `main`

## After a deploy, check

<!-- What Skye looks at once a merge has deployed. /merge lists these; it never checks them itself. Delete the section if nothing deploys. -->

- the new deployment succeeded
- the deploy log shows the health check passing
- if the PR has migrations, the migrate step succeeded
- anything the PR's "How to test" says to do after merging

## Releases

<!-- Optional. When /merge should suggest a release (it never creates one). Delete the section if this project doesn't do releases. -->

- when a milestone has no open issues left: `v1.0.0` when M2 finishes (v1 complete); after that, a new MINOR version (`v1.1.0`) for features, or a PATCH (`v1.0.1`) for a fix-only batch
