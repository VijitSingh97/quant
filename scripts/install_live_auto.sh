#!/bin/zsh
# Install (or reinstall) the hourly AUTO-ROTATING PAPER allocator as a launchd agent.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.vijit.basis.auto"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/data"
sed "s|__ROOT__|$ROOT|g" "$ROOT/deploy/$LABEL.plist" > "$DEST"

launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$DEST"
launchctl enable "$DOMAIN/$LABEL" 2>/dev/null || true

echo "Installed $LABEL -> $DEST  (hourly AUTO-ROTATING PAPER cycle; RunAtLoad fires one now)"
launchctl list | grep basis || echo "  (not listed yet — give it a moment)"
echo "Logs: $ROOT/data/auto.{out,err}.log ; book -> data/live_auto.db"
echo "Watch it: BASIS_DB=live_auto.db make live-monitor   (or live-web)"
