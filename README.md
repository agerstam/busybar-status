# BUSY Bar Status

Local web controller for mirroring availability from a cloud status provider to a
BUSY Bar. The included configuration reads Outlook-derived presence from a Cloudflare
Worker, but any service that implements the documented JSON contract can be used.

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

## Custom cloud status provider

The controller does not require Cloudflare or Outlook. It periodically performs an
HTTP `GET` against one status endpoint. A custom provider can accept updates from any
number of arbitrary producers—another computer, an automation, a webhook, or a local
agent—as long as its read endpoint returns the effective status described below.

The two sides of a provider are conceptually separate:

```text
arbitrary producers --authenticated push--> custom provider
BUSY Bar controller <--GET current status--- custom provider
```

The provider is responsible for authenticating writes, resolving conflicts between
producers, expiring stale data, and returning one current status. The BUSY Bar
controller is a read-only consumer and does not push changes to the provider.

### Read endpoint requirements

The configured endpoint must:

- Accept an HTTP `GET` request.
- Return a successful `2xx` response within 10 seconds.
- Return a JSON object. `Content-Type: application/json` is recommended.
- Return the latest effective state rather than an event history or array.
- Avoid HTTP caching, or honor the controller's `Cache-Control: no-cache` request.

The current controller does not send authentication credentials to the status
endpoint. Keep the read response free of private calendar, application, URL, email,
or document details. Authenticate the provider's separate ingestion endpoint instead.
If the read endpoint must also be private, see **Authenticated read endpoints** below.

### JSON contract

The recommended complete response is:

```json
{
  "status": "busy",
  "until": "2026-08-29T15:30:00-07:00",
  "updated": "2026-08-29T22:05:12.403Z"
}
```

| Field | Required | Accepted value | Meaning |
| --- | --- | --- | --- |
| `status` | Yes | `busy`, `tentative`, `ooo`, `free` | Effective presence to display. Values are case-insensitive and surrounding whitespace is ignored. `idle` is accepted as a legacy alias for `free`. |
| `until` | No | ISO 8601 timestamp string or `null` | Next scheduled transition: when an occupied state ends, or when a Free state is expected to become busy. It also enables the optional `Free in …` or `Busy in …` rotation. |
| `updated` | No | ISO 8601 timestamp string or `null` | When the provider last calculated or received this state. It is shown in the web UI but does not control expiration. |

Although the implementation defaults a missing or unrecognized `status` to `free`,
providers should always send one of the documented values. Silently becoming Free is
intended as a safe compatibility fallback, not as input validation for a provider.
Unknown additional JSON fields are ignored, so providers may add metadata without
breaking this controller.

Valid minimal response:

```json
{
  "status": "free"
}
```

Free now, with the next scheduled busy period beginning at 4:00 PM:

```json
{
  "status": "free",
  "until": "2026-08-29T16:00:00-07:00",
  "updated": "2026-08-29T22:42:15Z"
}
```

Out of office with no known end time:

```json
{
  "status": "ooo",
  "until": null,
  "updated": "2026-08-29T17:00:00Z"
}
```

### Timestamp and timezone rules

Use an ISO 8601/RFC 3339 timestamp with an explicit UTC offset whenever possible:

```text
2026-08-29T15:30:00-07:00       Pacific daylight time
2026-12-15T15:30:00-08:00       Pacific standard time
2026-08-29T22:30:00Z            UTC
2026-08-29T22:30:00.403Z        UTC with fractional seconds
```

`Z` means UTC. Numeric offsets must include their sign and should use the `±HH:MM`
form. The provider should calculate the correct daylight-saving offset for the event
date rather than assuming that Pacific time is always `-07:00` or always `-08:00`.

A timestamp without an offset, such as `2026-08-29T15:30:00`, is accepted for
compatibility but is interpreted in the local timezone of the Mac running the
controller. That can produce different results after moving the controller or around
daylight-saving transitions. Custom providers should therefore always include `Z` or
an explicit offset.

Invalid timestamps are treated as if the field were absent. If `until` is already in
the past, it is cleared; an expired non-Free status is changed to `free` until the next
provider poll. `updated` is informational and is not used as a freshness guarantee,
so the provider itself must expire stale producer reports.

### Push/ingestion guidance

The provider's write API is deliberately not prescribed, but a practical ingestion
payload from an arbitrary source could look like this:

```json
{
  "source_id": "work-laptop",
  "status": "busy",
  "until": "2026-08-29T15:30:00-07:00",
  "observed_at": "2026-08-29T22:05:12.403Z",
  "expires_in_seconds": 90
}
```

This is an example producer-to-provider format, not the controller's GET response.
Give every producer a stable source ID and separate revocable credential. Providers
should use their own receipt time for freshness, reject delayed sequence numbers when
applicable, and automatically remove reports that stop receiving heartbeats. Do not
allow a sleeping or disconnected computer to leave a permanent Busy status.

### Configure a different endpoint

The status URL is currently a source-code constant near the top of
`busybar-controller.py`:

```python
STATUS_URL = "https://busybar-status.matsagerstam.workers.dev/status"
```

Replace it with the HTTPS URL of the custom provider's read endpoint:

```python
STATUS_URL = "https://status.example.com/api/current"
```

Verify the provider independently before running the controller:

```bash
curl --fail --silent --show-error \
  -H 'Cache-Control: no-cache' \
  'https://status.example.com/api/current'
```

The output must be a single JSON object matching the contract above.

For development, stop the installed controller if it is running and launch the source
version:

```bash
.venv/bin/python busybar-controller.py
```

For the installed application, rebuild and restart it after changing the constant:

```bash
make install
```

Use **Force Sync Now** in the General tab to test the endpoint immediately. Provider
HTTP errors, timeouts, and invalid JSON are reported in the Controller status and the
controller log. The last displayed BUSY Bar state remains in place when a poll fails.

### Authenticated read endpoints

To send a bearer token, change the request in `Controller.poll()` from:

```python
r = requests.get(STATUS_URL, headers={"Cache-Control":"no-cache"}, timeout=10)
```

to an environment-backed header, for example:

```python
token = os.environ["BUSYBAR_STATUS_TOKEN"]
r = requests.get(
    STATUS_URL,
    headers={
        "Cache-Control": "no-cache",
        "Authorization": f"Bearer {token}",
    },
    timeout=10,
)
```

Never put the token itself in `busybar-controller.py`, a simulator script, or a Git
commit. When packaging the macOS application, the LaunchAgent also needs access to the
environment variable; alternatively, implement a secure local secret-loading method
appropriate for the deployment.

## Features and device notes

Manual card display is available while work synchronization is off. Manual mode also
supports scrolling text with foreground and background colors. The device API accepts
1–120 printable ASCII characters; its bitmap font does not support emoji or other
Unicode characters.

The Free mapping defaults to **Display off**, but it can use any built-in or custom
card instead. While work synchronization is enabled, **Show time until next change**
can alternate the mapped card with a concise relative message such as `Free in 45m`,
`Free in 2h 5m`, or `Busy in 20m`. The interval is configurable from 5 to 300 seconds,
and both settings are persisted with the other controller configuration.

The dashboard's **On device now** panel samples the real front display every 15
seconds, including changes made from the device or mobile app. Screenshots are
coalesced by the controller for 12 seconds to avoid unnecessary device API traffic.
Automatic dashboard updates preserve configuration edits until they are saved or the
page is reloaded.

Muting stores the current non-zero volume so enabling sound restores it. Built-in
themes use a device-native animation format. With work sync off, use **Capture real
theme previews** once to render each theme on the device and cache accurate thumbnails.
