#!/bin/bash
#
# Sets up (or removes) the daily production backups on this Mac (#19).
#
#   bash backup/install.sh              Install, or update after changing backup.sh
#   bash backup/install.sh --uninstall  Stop the scheduled job (backups are kept)
#
# Run it from the repo folder, logged in to the Railway CLI. It:
#   1. copies backup.sh into ~/Backups/hicc-choir-ops/, because a
#      launchd job may not be allowed to run a script from Documents (where
#      this repo lives) under macOS privacy protection;
#   2. writes a small config file there with the Railway CLI's full path and
#      this project's ID, read from `railway status` so neither is committed;
#   3. writes a launchd job that runs `backup.sh run` every day at 10am and
#      at login, and loads it.

set -eu

BACKUP_DIR="$HOME/Backups/hicc-choir-ops"
JOB_LABEL="com.hicc-choir-ops.backup"
PLIST="$HOME/Library/LaunchAgents/$JOB_LABEL.plist"
DOMAIN="gui/$(id -u)"   # launchd's name for jobs that run as you while you're logged in

# Unload the job if it's loaded. Ignore the error when it isn't.
unload_job() {
  launchctl bootout "$DOMAIN/$JOB_LABEL" 2>/dev/null || true
}

if [ "${1:-}" = "--uninstall" ]; then
  unload_job
  rm -f "$PLIST"
  echo "Scheduled backups stopped. Existing backups are still in $BACKUP_DIR"
  exit 0
fi

# Work from the repo folder, so `railway status` finds the linked project.
cd "$(dirname "$0")/.."

RAILWAY_BIN=$(command -v railway) || { echo "The Railway CLI isn't installed." >&2; exit 1; }
PROJECT_ID=$("$RAILWAY_BIN" status --json | /usr/bin/python3 -c 'import json, sys; print(json.load(sys.stdin)["id"])') \
  || { echo "Couldn't read the project from 'railway status'. Are you logged in (railway login)?" >&2; exit 1; }

mkdir -p "$BACKUP_DIR" "$HOME/Library/LaunchAgents"
chmod 700 "$BACKUP_DIR"   # backups hold real names, so only you can open the folder

cp backup/backup.sh "$BACKUP_DIR/backup.sh"
chmod 700 "$BACKUP_DIR/backup.sh"

cat > "$BACKUP_DIR/config" <<EOF
# Written by backup/install.sh. Rerun it rather than editing this file.
# A RAILWAY_PROJECT_ID given when running backup.sh wins over this one, so
# the failure alert can be tested with a made-up ID (see README, Backups).
RAILWAY_BIN="$RAILWAY_BIN"
RAILWAY_PROJECT_ID="\${RAILWAY_PROJECT_ID:-$PROJECT_ID}"
EOF

# The launchd job. StartCalendarInterval runs it daily at 10:00; if the Mac is
# asleep then, launchd runs it when it wakes. RunAtLoad also runs it at login,
# which catches up a day the Mac was switched off at 10am. Output that isn't
# in backup.log (e.g. a crash) goes to launchd-output.log, for debugging.
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$JOB_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$BACKUP_DIR/backup.sh</string>
    <string>run</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>10</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$BACKUP_DIR/launchd-output.log</string>
  <key>StandardErrorPath</key>
  <string>$BACKUP_DIR/launchd-output.log</string>
</dict>
</plist>
EOF

# Reload, so a reinstall picks up any changes.
unload_job
launchctl bootstrap "$DOMAIN" "$PLIST"

echo "Installed. Backups go to $BACKUP_DIR"
echo "Check on them any time with: $BACKUP_DIR/backup.sh status"
