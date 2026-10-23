#!/bin/bash
#
# Daily backups of production's database, made on Skye's Mac (#19).
#
# Railway's Hobby plan has no database backups, so this script makes them:
# it asks the Railway CLI to run pg_dump inside production's Postgres
# service, compresses the result here, checks it's complete, and keeps the
# newest few. No database password is stored anywhere; it uses the Railway
# CLI's own login.
#
# backup/install.sh copies this script into the backup folder and sets up a
# launchd job that runs it every morning. Commands:
#
#   backup.sh run     The scheduled check: back up only if no backup exists yet
#                     for today's date (US Eastern), otherwise note the check
#                     and stop.
#   backup.sh now     Back up right away, whatever the age of the last one.
#   backup.sh status  Show the newest backup, how many are kept, whether the
#                     scheduled job is loaded, and the last few log lines.
#
# Every attempt is logged to backup.log. A good backup shows a notification;
# a failed one shows an alert that stays on screen until it's dismissed.
#
# Written for macOS's built-in bash 3.2, so it avoids newer bash features.

set -u -o pipefail

# --- Settings ---------------------------------------------------------------

# Outside Documents, Desktop and iCloud Drive on purpose: macOS privacy
# protection can stop a launchd job from reading or writing those folders.
BACKUP_DIR="$HOME/Backups/hicc-choir-ops"
LOG_FILE="$BACKUP_DIR/backup.log"
# The Railway CLI's own messages from the latest attempt (e.g. its SSH key
# notice, or why it couldn't connect). Overwritten each time, so backup.log
# stays one line per attempt.
OUTPUT_FILE="$BACKUP_DIR/last-run-output.log"
KEEP=30           # how many backups to keep (about a month of daily ones)
# The Postgres service's name in the Railway project. This project shares one
# Railway project with heritage-media-availability, so the name has a suffix.
POSTGRES_SERVICE="Postgres-KuxJ"
# "Today" and the dates in file names use US Eastern time, like the rest of
# the app (CLAUDE.md, Conventions), whatever time zone the Mac is set to.
TIMEZONE="America/New_York"
JOB_LABEL="com.hicc-choir-ops.backup"

# install.sh writes RAILWAY_BIN (the CLI's full path, since launchd doesn't
# know your shell's PATH) and RAILWAY_PROJECT_ID (so this works outside the
# repo folder) into this file. They're IDs and paths, not secrets.
CONFIG_FILE="$BACKUP_DIR/config"

# --- Helpers ----------------------------------------------------------------

# Append a timestamped line to backup.log. When run by hand in Terminal, also
# show it there; under launchd, stay quiet so launchd-output.log only
# collects unexpected errors.
log() {
  local line
  line="$(date '+%Y-%m-%d %H:%M:%S')  $1"
  echo "$line" >> "$LOG_FILE"
  if [ -t 1 ]; then echo "$line"; fi
}

# A macOS notification banner. The text is passed as arguments rather than
# pasted into the AppleScript, so quotes in a message can't break it.
notify() {
  osascript -e 'on run argv' \
            -e 'display notification (item 2 of argv) with title (item 1 of argv)' \
            -e 'end run' "$1" "$2" >/dev/null 2>&1
}

# An alert that stays on screen until it's dismissed, for failures, so one
# can't slip by unnoticed the way a banner might.
alert() {
  osascript -e 'on run argv' \
            -e 'display alert (item 1 of argv) message (item 2 of argv) as critical' \
            -e 'end run' "$1" "$2" >/dev/null 2>&1
}

# The newest backup's path, or nothing if there are none. Names start with
# the date and time, so sorting by name sorts by age.
newest_backup() {
  ls -1 "$BACKUP_DIR"/hicc-*.sql.gz 2>/dev/null | sort | tail -n 1
}

# How many whole days ago a file was last changed.
age_in_days() {
  local modified now
  modified=$(stat -f %m "$1")
  now=$(date +%s)
  echo $(( (now - modified) / 86400 ))
}

# The newest backup's age in words, for messages ("3 days ago").
newest_age_words() {
  local newest days
  newest=$(newest_backup)
  if [ -z "$newest" ]; then
    echo "none yet"
    return
  fi
  days=$(age_in_days "$newest")
  case "$days" in
    0) echo "today" ;;
    1) echo "1 day ago" ;;
    *) echo "$days days ago" ;;
  esac
}

# Log a failure, remove any half-written file, and show the alert.
fail() {
  rm -f "$BACKUP_DIR/.in-progress.sql.gz"
  log "FAILED: $1"
  alert "HICC backup failed" "$1

Last good backup: $(newest_age_words).
Details: $OUTPUT_FILE"
  exit 1
}

# --- Making a backup --------------------------------------------------------

backup_now() {
  local tmp final size kept

  # Load RAILWAY_BIN and RAILWAY_PROJECT_ID (see CONFIG_FILE above).
  [ -f "$CONFIG_FILE" ] && . "$CONFIG_FILE"
  if [ -z "${RAILWAY_BIN:-}" ] || [ -z "${RAILWAY_PROJECT_ID:-}" ]; then
    fail "Not set up yet. Run backup/install.sh from the repo folder."
  fi

  # An expired Railway login is the most likely failure, so check it first
  # and say exactly how to fix it.
  if ! "$RAILWAY_BIN" whoami >"$OUTPUT_FILE" 2>&1; then
    fail "The Railway login has expired. Run: railway login"
  fi

  # pg_dump runs inside production's Postgres service, so its version always
  # matches the server's (pg_dump refuses to dump a newer server). It reads
  # the connection details from that service's own PG* variables.
  #   --no-owner, --no-privileges: leave out Railway's user names, so the
  #   backup restores into any database, including a local test one.
  # The dump comes back as plain text and is compressed here; a half-written
  # file never takes a real backup's name.
  tmp="$BACKUP_DIR/.in-progress.sql.gz"
  if ! "$RAILWAY_BIN" ssh --project "$RAILWAY_PROJECT_ID" --service "$POSTGRES_SERVICE" \
        --environment production -- pg_dump --no-owner --no-privileges \
        2>"$OUTPUT_FILE" | gzip > "$tmp"; then
    fail "pg_dump didn't finish. Railway may be down, or the connection dropped."
  fi

  # A dump that was cut off still looks like a file, so check pg_dump's last
  # words are there. Newer versions add a line or two after them, hence the
  # last 20 lines rather than the very last one.
  if ! gzip -t "$tmp" 2>/dev/null \
     || ! gunzip -c "$tmp" | tail -n 20 | grep -q 'PostgreSQL database dump complete'; then
    fail "The backup was empty or incomplete, so it wasn't kept."
  fi

  final="$BACKUP_DIR/hicc-$(TZ=$TIMEZONE date '+%Y-%m-%d-%H%M').sql.gz"
  mv "$tmp" "$final"
  chmod 600 "$final"   # it holds real member names and emails, so only you can read it

  # Keep the newest $KEEP, oldest removed first.
  ls -1 "$BACKUP_DIR"/hicc-*.sql.gz | sort -r | tail -n +$((KEEP + 1)) | while read -r old; do
    rm -f "$old"
  done

  size=$(du -h "$final" | cut -f1 | tr -d ' ')
  kept=$(ls -1 "$BACKUP_DIR"/hicc-*.sql.gz | wc -l | tr -d ' ')
  log "OK: $(basename "$final") ($size), $kept kept"
  notify "HICC backup saved" "$(basename "$final") ($size). $kept kept."
}

# --- Commands ---------------------------------------------------------------

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

case "${1:-}" in
  run)
    # The launchd job runs this at 10am and at login, so a day missed while
    # the Mac was off is caught up when it's next on. The date is in the file
    # name (Eastern), so "already backed up today" doesn't depend on hours.
    newest=$(newest_backup)
    today=$(TZ=$TIMEZONE date '+%Y-%m-%d')
    if [ -n "$newest" ] && [[ "$(basename "$newest")" == hicc-"$today"-* ]]; then
      # Logged so status shows the job is alive, but no notification.
      log "Checked: newest backup is from $(newest_age_words), nothing to do"
      exit 0
    fi
    backup_now
    ;;
  now)
    backup_now
    ;;
  status)
    echo "Backup folder:  $BACKUP_DIR"
    newest=$(newest_backup)
    if [ -n "$newest" ]; then
      echo "Newest backup:  $(basename "$newest") ($(newest_age_words))"
    else
      echo "Newest backup:  none yet"
    fi
    echo "Backups kept:   $(ls -1 "$BACKUP_DIR"/hicc-*.sql.gz 2>/dev/null | wc -l | tr -d ' ') (up to $KEEP)"
    if launchctl print "gui/$(id -u)/$JOB_LABEL" >/dev/null 2>&1; then
      echo "Scheduled job:  loaded (checks daily at 10am and at login)"
    else
      echo "Scheduled job:  NOT loaded. Run backup/install.sh from the repo folder."
    fi
    echo
    echo "Recent log:"
    tail -n 5 "$LOG_FILE" 2>/dev/null || echo "  (nothing logged yet)"
    ;;
  *)
    echo "Usage: $(basename "$0") run|now|status" >&2
    exit 2
    ;;
esac
