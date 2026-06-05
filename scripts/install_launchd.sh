#!/bin/zsh
# Install (or reinstall) the hourly btcvol logger as a launchd user agent.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.vijit.btcvol.logger"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/data"

# Render the template with this machine's absolute project path.
sed "s|__ROOT__|$ROOT|g" "$ROOT/deploy/$LABEL.plist" > "$DEST"

# Replace any existing instance, then load. RunAtLoad fires one row immediately.
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$DEST"
launchctl enable "$DOMAIN/$LABEL" 2>/dev/null || true

echo "Installed $LABEL -> $DEST"
echo "Status:"
launchctl list | grep btcvol || echo "  (not listed yet — give it a moment)"
echo "Logs: $ROOT/data/launchd.{out,err}.log ; data -> $ROOT/data/timeseries.csv"
