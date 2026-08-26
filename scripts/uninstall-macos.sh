#!/bin/sh
set -eu

LABEL="com.matsagerstam.busybar-status"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"
APP_PATH="$HOME/Applications/BUSY Bar Status.app"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
if [ -f "$PLIST_PATH" ]; then
  mv "$PLIST_PATH" "$HOME/.Trash/$LABEL.plist"
fi
if [ -d "$APP_PATH" ]; then
  mv "$APP_PATH" "$HOME/.Trash/BUSY Bar Status.app"
fi

echo "BUSY Bar Status was stopped and removed from login startup."
echo "Configuration, environment, project files, and logs were preserved."
