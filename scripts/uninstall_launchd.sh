#!/bin/zsh
# Remove the btcvol logger launchd agent.
LABEL="com.vijit.btcvol.logger"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
rm -f "$DEST"
echo "Removed $LABEL (plist deleted, agent unloaded). data/ is left intact."
