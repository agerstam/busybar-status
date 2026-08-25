#!/usr/bin/env python3

import sys
import time
from datetime import datetime, timezone

import requests


# ============================================================
# CONFIGURATION
# ============================================================

# BUSY Bar connection
BUSYBAR_IP = "10.0.4.20"
BUSYBAR_BASE_URL = f"http://{BUSYBAR_IP}"

# Leave blank for USB / API access without a token.
BUSYBAR_API_TOKEN = ""


# Cloudflare status endpoint
STATUS_URL = "https://busybar-status.matsagerstam.workers.dev/status"


# ------------------------------------------------------------
# STATUS -> BUSY BAR IMAGE/THEME MAPPING
#
# These are intentionally kept here at the top so they're
# trivial to change later.
# ------------------------------------------------------------

BUSY_THEME = "meeting"

OOO_THEME = "keep_out"

TENTATIVE_THEME = "booked"


# BUSY Bar profile slots
BUSY_SLOT = "busy"
TENTATIVE_SLOT = "custom"
OOO_SLOT = "busy"


# Poll Cloudflare every N seconds
POLL_INTERVAL_SECONDS = 30


# Small delays between virtual button presses / profile changes.
DEVICE_SETTLE_SECONDS = 0.5


# HTTP timeouts
BUSYBAR_TIMEOUT_SECONDS = 5
STATUS_TIMEOUT_SECONDS = 10


# If Cloudflare provides an "until" timestamp and that time has
# already passed, consider the state FREE.
#
# This protects against a stale BUSY state if the Windows sender
# temporarily stops updating Cloudflare.
HONOR_UNTIL_TIMESTAMP = True


# ============================================================
# HTTP SESSION
# ============================================================

session = requests.Session()

busybar_headers = {}

if BUSYBAR_API_TOKEN:
    busybar_headers["X-API-Token"] = BUSYBAR_API_TOKEN


# ============================================================
# LOGGING
# ============================================================

def log(message):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}", flush=True)


# ============================================================
# BUSY BAR REST API
# ============================================================

def busybar_get(path):
    response = session.get(
        BUSYBAR_BASE_URL + path,
        headers=busybar_headers,
        timeout=BUSYBAR_TIMEOUT_SECONDS,
    )

    response.raise_for_status()
    return response.json()


def busybar_put(path, payload):
    response = session.put(
        BUSYBAR_BASE_URL + path,
        headers=busybar_headers,
        json=payload,
        timeout=BUSYBAR_TIMEOUT_SECONDS,
    )

    response.raise_for_status()

    if response.content:
        return response.json()

    return None


def busybar_post(path, params=None):
    response = session.post(
        BUSYBAR_BASE_URL + path,
        headers=busybar_headers,
        params=params,
        timeout=BUSYBAR_TIMEOUT_SECONDS,
    )

    response.raise_for_status()

    if response.content:
        return response.json()

    return None


# ============================================================
# BUSY BAR PROFILE CONTROL
# ============================================================

def get_profile(slot):
    return busybar_get(
        f"/api/busy/profiles/{slot}"
    )


def configure_profile(slot, theme):
    """
    Configure an existing BUSY Bar slot with:

      - requested theme
      - INFINITE timer
      - fresh profile timestamp

    Existing title/id/settings are otherwise preserved.
    """

    profile = get_profile(slot)

    old_theme = profile.get(
        "busy_bar_settings", {}
    ).get("theme")

    old_timer = profile.get(
        "timer_settings", {}
    ).get("type")

    log(
        f"Configuring '{slot}' profile: "
        f"{old_theme}/{old_timer} -> {theme}/INFINITE"
    )

    profile["timer_settings"] = {
        "type": "INFINITE"
    }

    profile.setdefault(
        "busy_bar_settings", {}
    )

    profile["busy_bar_settings"]["theme"] = theme

    # IMPORTANT:
    # Give every profile mutation a fresh timestamp.
    profile["profile_timestamp_ms"] = int(
        time.time() * 1000
    )

    result = busybar_put(
        f"/api/busy/profiles/{slot}",
        profile,
    )

    log(
        f"Profile PUT result: {result}"
    )

    time.sleep(DEVICE_SETTLE_SECONDS)

    # Verify that firmware actually accepted the profile update.
    current = get_profile(slot)

    actual_theme = current.get(
        "busy_bar_settings", {}
    ).get("theme")

    actual_timer = current.get(
        "timer_settings", {}
    ).get("type")

    if actual_theme != theme:
        raise RuntimeError(
            f"BUSY Bar did not apply theme "
            f"'{theme}' to slot '{slot}'. "
            f"Read-back theme is '{actual_theme}'."
        )

    if actual_timer != "INFINITE":
        raise RuntimeError(
            f"BUSY Bar did not apply INFINITE timer "
            f"to slot '{slot}'. "
            f"Read-back timer is '{actual_timer}'."
        )

    log(
        f"Verified '{slot}': "
        f"theme={actual_theme}, timer={actual_timer}"
    )


# ============================================================
# VIRTUAL BUTTON CONTROL
# ============================================================

def press(key):
    log(
        f"BUSY Bar input: {key}"
    )

    result = busybar_post(
        "/api/input",
        params={
            "key": key
        },
    )

    log(
        f"Input result: {result}"
    )

    time.sleep(DEVICE_SETTLE_SECONDS)


def stop_current_display():
    """
    Equivalent to pressing OFF on the BUSY Bar.
    """

    press("off")


def start_profile(slot):
    """
    Select a profile slot and then press START.

    slot must be:
      busy
      custom
    """

    if slot not in ("busy", "custom"):
        raise ValueError(
            f"Unsupported BUSY Bar slot: {slot}"
        )

    press(slot)
    press("start")


# ============================================================
# CLOUD STATUS
# ============================================================

def parse_until(value):
    if not value:
        return None

    try:
        # Python understands +00:00 more consistently than Z.
        value = value.replace(
            "Z",
            "+00:00"
        )

        return datetime.fromisoformat(value)

    except Exception:
        return None


def get_cloud_status():
    response = session.get(
        STATUS_URL,
        headers={
            "Cache-Control": "no-cache"
        },
        timeout=STATUS_TIMEOUT_SECONDS,
    )

    response.raise_for_status()

    data = response.json()

    status = str(
        data.get("status", "free")
    ).strip().lower()

    until = parse_until(
        data.get("until")
    )

    if status not in {
        "free",
        "busy",
        "tentative",
        "ooo",
    }:
        log(
            f"Unknown cloud status '{status}', "
            f"treating as FREE."
        )
        status = "free"

    # Optional safety net:
    # If the event has expired but Cloudflare hasn't been
    # refreshed yet, clear the bar.
    if (
        HONOR_UNTIL_TIMESTAMP
        and status != "free"
        and until is not None
    ):
        now = datetime.now(timezone.utc)

        if until <= now:
            log(
                f"Cloud state '{status}' expired at "
                f"{until.isoformat()}, treating as FREE."
            )

            status = "free"

    return status, until, data

    # ============================================================
# STATE MACHINE
# ============================================================

def activate_state(state):
    """
    Translate calendar state into native BUSY Bar behavior.
    """

    log(
        f"Activating state: {state.upper()}"
    )

    # Always leave the currently-running BUSY/CUSTOM session
    # before modifying profiles or switching modes.
    stop_current_display()

    if state == "free":
        log(
            "BUSY Bar is FREE."
        )
        return

    if state == "busy":
        configure_profile(
            BUSY_SLOT,
            BUSY_THEME,
        )

        start_profile(
            BUSY_SLOT
        )

        return

    if state == "tentative":
        configure_profile(
            TENTATIVE_SLOT,
            TENTATIVE_THEME,
        )

        start_profile(
            TENTATIVE_SLOT
        )

        return

    if state == "ooo":
        configure_profile(
            OOO_SLOT,
            OOO_THEME,
        )

        start_profile(
            OOO_SLOT
        )

        return

    raise ValueError(
        f"Unexpected state: {state}"
    )

    # ============================================================
# MAIN LOOP
# ============================================================

def main():
    log("BUSY Bar calendar controller starting.")

    log(
        f"BUSY Bar: {BUSYBAR_BASE_URL}"
    )

    log(
        f"Cloud status: {STATUS_URL}"
    )

    log(
        "Theme mapping: "
        f"busy={BUSY_THEME}, "
        f"tentative={TENTATIVE_THEME}, "
        f"ooo={OOO_THEME}"
    )

    current_state = None

    while True:

        try:
            new_state, until, raw = get_cloud_status()

            until_text = (
                until.isoformat()
                if until
                else "none"
            )

            log(
                f"Cloud status: "
                f"{new_state}, until={until_text}"
            )

            # The important bit:
            #
            # Do NOT continuously reprogram the BUSY Bar.
            # Only touch it when the calendar state changes.
            if new_state != current_state:

                log(
                    f"State transition: "
                    f"{current_state} -> {new_state}"
                )

                activate_state(
                    new_state
                )

                # Only record the new state AFTER all BUSY Bar
                # operations completed successfully.
                current_state = new_state

            else:
                log(
                    f"No state change ({current_state})."
                )

        except requests.RequestException as exc:
            log(
                f"Network/API error: {exc}"
            )

        except Exception as exc:
            log(
                f"ERROR: {exc}"
            )

        time.sleep(
            POLL_INTERVAL_SECONDS
        )


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        log(
            "Controller stopped."
        )

        sys.exit(0)