# BUSY Bar Status

Local web controller for mirroring Outlook availability from Cloudflare to a BUSY Bar.

## Requirements

- macOS with Python 3 and `make`
- A BUSY Bar reachable from the Mac over its USB Ethernet connection
- The BUSY Bar device IP address, if it is different from the default `10.0.4.20`

The installer creates a local Python virtual environment and uses PyInstaller to build
the application. No system-wide Python packages are installed.

Check that the required commands are available:

```bash
python3 --version
make --version
```

If `python3` is missing, install Python 3 from <https://www.python.org/downloads/macos/>
or with Homebrew (`brew install python`). If `make` is missing, install Apple's
Command Line Tools with `xcode-select --install`.

## Install on macOS

### 1. Get the project

Clone the repository and enter its directory:

```bash
git clone https://github.com/agerstam/busybar-status.git
cd busybar-status
```

If the project is already on the Mac, open Terminal and `cd` to its directory instead.

### 2. Connect the BUSY Bar

Connect the device using its USB Ethernet connection and make sure the Mac can reach
its configured IP address. The default device address is `10.0.4.20`.

### 3. Install the background service

From the project directory, run:

```bash
make install
```

The installer:

1. Creates or updates `.venv` in the project directory.
2. Installs the runtime and build dependencies into that environment.
3. Builds `~/Applications/BUSY Bar Status.app`.
4. Registers a per-user LaunchAgent that starts the controller at login.
5. Starts the controller and opens <http://127.0.0.1:8765>.

No Terminal window needs to remain open. On first installation, allow **BUSY Bar
Status** to access the local network when macOS asks. This permission can be changed
later under **System Settings → Privacy & Security → Local Network**.

### 4. Configure and verify

Open <http://127.0.0.1:8765> and review the device settings. The UI can discover the
device's built-in themes and saved Draw Tool images, map availability states to cards,
preview custom images, and control sound and volume.

To check the installed service's output:

```bash
tail -f "$HOME/Library/Logs/BusyBarStatus/controller.log"
```

Errors are written to `controller-error.log` in the same directory.

### Updating

Pull the latest project changes and run the installer again:

```bash
git pull
make install
```

The installer rebuilds the app and restarts the LaunchAgent. Run the installer again
after moving the project directory because the LaunchAgent stores its absolute path.

## Uninstall

Stop the controller and remove the app and login startup entry with:

```bash
make uninstall
```

The uninstall script moves the app and LaunchAgent file to the macOS Trash. It
preserves the project directory, settings, preview cache, and logs. To remove those
manually, delete:

```text
~/Library/Application Support/BusyBarStatus
~/Library/Logs/BusyBarStatus
```

## Run for development

To run the controller directly without building the macOS app:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python busybar-controller.py
```

Open <http://127.0.0.1:8765>. Development settings persist in the project-level
`config.json`.

Set `BUSYBAR_API_TOKEN` in the same Terminal session before starting the development
server if the device requires an API key:

```bash
export BUSYBAR_API_TOKEN="your-token"
.venv/bin/python busybar-controller.py
```

The simulator authenticates to the Cloudflare Worker with a separate environment
variable:

```bash
export BUSYBAR_WORKER_TOKEN="your-worker-token"
./busybar-sim.sh busy 5
```

The token previously embedded in the simulator should be revoked or rotated at the
worker/provider. It must not be committed to the repository again.

## Features and device notes

Manual card display is available while work synchronization is off. Manual mode also
supports scrolling text with foreground and background colors. The device API accepts
1–120 printable ASCII characters; its bitmap font does not support emoji or other
Unicode characters.

Muting stores the current non-zero volume so enabling sound restores it. Built-in
themes use a device-native animation format. With work sync off, use **Capture real
theme previews** once to render each theme on the device and cache accurate thumbnails.
