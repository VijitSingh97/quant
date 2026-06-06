#!/bin/zsh
# Remove the paper carry-engine launchd agent.
LABEL="com.vijit.basis.paper"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$DEST"
echo "Removed $LABEL (agent unloaded, plist deleted). data/live.db is left intact."
