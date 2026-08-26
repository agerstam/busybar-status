#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VENV_DIR="$PROJECT_DIR/.venv"
LABEL="com.matsagerstam.busybar-status"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs/BusyBarStatus"
APP_DIR="$HOME/Applications/BUSY Bar Status.app"
APP_EXECUTABLE="$APP_DIR/Contents/MacOS/BUSY Bar Status"
DATA_DIR="$HOME/Library/Application Support/BusyBarStatus"

echo "Installing BUSY Bar Status from $PROJECT_DIR"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$PROJECT_DIR/requirements.txt"
"$VENV_DIR/bin/pip" install -r "$PROJECT_DIR/requirements-build.txt"
mkdir -p "$PLIST_DIR" "$LOG_DIR" "$HOME/Applications" "$DATA_DIR"

if [ -f "$PROJECT_DIR/config.json" ] && [ ! -f "$DATA_DIR/config.json" ]; then
  cp "$PROJECT_DIR/config.json" "$DATA_DIR/config.json"
fi
if [ -d "$PROJECT_DIR/.preview-cache" ] && [ ! -d "$DATA_DIR/.preview-cache" ]; then
  cp -R "$PROJECT_DIR/.preview-cache" "$DATA_DIR/.preview-cache"
fi

"$VENV_DIR/bin/pyinstaller" \
  --clean --noconfirm --windowed \
  --name "BUSY Bar Status" \
  --osx-bundle-identifier "$LABEL" \
  --add-data "$PROJECT_DIR/web:web" \
  --distpath "$PROJECT_DIR/dist" \
  --workpath "$PROJECT_DIR/build" \
  "$PROJECT_DIR/busybar-controller.py"

rm -rf "$APP_DIR"
ditto "$PROJECT_DIR/dist/BUSY Bar Status.app" "$APP_DIR"
/usr/libexec/PlistBuddy -c "Add :NSLocalNetworkUsageDescription string BUSY Bar Status connects to your BUSY Bar over USB Ethernet." "$APP_DIR/Contents/Info.plist" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Set :NSLocalNetworkUsageDescription BUSY Bar Status connects to your BUSY Bar over USB Ethernet." "$APP_DIR/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$APP_DIR/Contents/Info.plist" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Set :LSUIElement true" "$APP_DIR/Contents/Info.plist"
codesign --force --deep --sign - "$APP_DIR"

sed \
  -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
  -e "s|__APP_EXECUTABLE__|$APP_EXECUTABLE|g" \
  -e "s|__LOG_DIR__|$LOG_DIR|g" \
  "$PROJECT_DIR/scripts/com.matsagerstam.busybar-status.plist.template" \
  > "$PLIST_PATH"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
pkill -x "BUSY Bar Status" 2>/dev/null || true
pkill -f "$PROJECT_DIR/busybar-controller.py" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
launchctl enable "gui/$(id -u)/$LABEL"
launchctl kickstart -k "gui/$(id -u)/$LABEL"

echo "Installed $APP_DIR"
echo "The controller is started automatically at login."
echo "Opening http://127.0.0.1:8765"
open "http://127.0.0.1:8765"
