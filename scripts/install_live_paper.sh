#!/bin/zsh
# Install (or reinstall) the hourly PAPER carry engine as a launchd user agent.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.vijit.basis.paper"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/data"

# Migration: shed the pre-rename agent (com.vijit.btcvol.paper) if still loaded.
launchctl bootout "$DOMAIN/com.vijit.btcvol.paper" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/com.vijit.btcvol.paper.plist"

sed "s|__ROOT__|$ROOT|g" "$ROOT/deploy/$LABEL.plist" > "$DEST"

launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$DEST"
launchctl enable "$DOMAIN/$LABEL" 2>/dev/null || true

echo "Installed $LABEL -> $DEST  (hourly PAPER reconcile; RunAtLoad fires one now)"
launchctl list | grep basis || echo "  (not listed yet — give it a moment)"
echo "Logs: $ROOT/data/paper.{out,err}.log ; book -> data/live.db ; status: make live-monitor"
