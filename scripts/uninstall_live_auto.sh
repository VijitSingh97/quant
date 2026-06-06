#!/bin/zsh
# Remove the auto-rotating paper allocator launchd agent.
LABEL="com.vijit.basis.auto"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$DEST"
echo "Removed $LABEL (agent unloaded, plist deleted). data/live_auto.db is left intact."
