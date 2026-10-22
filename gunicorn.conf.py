"""Settings for gunicorn, the web server that runs Django in production.

gunicorn loads this file automatically when started from the project folder, so
Railway's start command can stay short: `gunicorn config.wsgi`. Locally we use
`manage.py runserver` instead.
"""

# No `bind` setting: gunicorn listens on 0.0.0.0:$PORT on its own whenever the PORT
# environment variable is set, which is how Railway tells an app which port to use.

# Two worker processes: one can answer while the other is busy. Plenty for a choir's
# worth of users, and well inside the Hobby plan's memory.
workers = 2

# One line per request ("-" means the console) so Railway's Logs tab shows every visit.
accesslog = "-"
