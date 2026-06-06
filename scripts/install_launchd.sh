#!/bin/zsh
# Install (or reinstall) the hourly basis logger as a launchd user agent.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.vijit.basis.logger"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/data"

# Migration: shed the pre-rename agent (com.vijit.btcvol.logger) if still loaded.
launchctl bootout "$DOMAIN/com.vijit.btcvol.logger" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/com.vijit.btcvol.logger.plist"

# Render the template with this machine's absolute project path.
sed "s|__ROOT__|$ROOT|g" "$ROOT/deploy/$LABEL.plist" > "$DEST"

# Replace any existing instance, then load. RunAtLoad fires one row immediately.
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$DEST"
launchctl enable "$DOMAIN/$LABEL" 2>/dev/null || true

echo "Installed $LABEL -> $DEST"
echo "Status:"
launchctl list | grep basis || echo "  (not listed yet — give it a moment)"
echo "Logs: $ROOT/data/launchd.{out,err}.log ; data -> $ROOT/data/timeseries.csv"
