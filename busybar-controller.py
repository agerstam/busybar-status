#!/usr/bin/env python3

import os
import sys
import time
from datetime import datetime

import requests
from busylib import BusyBar, types


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

BUSYBAR_IP = os.getenv("BUSYBAR_IP", "192.168.84.66")
BUSYBAR_TOKEN = os.getenv("BUSYBAR_TOKEN")

CLOUDFLARE_STATUS_URL = os.getenv("CLOUDFLARE_STATUS_URL", "")
POLL_SECONDS = int(os.getenv("BUSYBAR_POLL_SECONDS", "30"))

# Don't reprogram a timer merely because a few seconds have elapsed.
# If the device already has the correct profile and its remaining time
# is within this tolerance of what the calendar predicts, leave it alone.
TIMER_TOLERANCE_SECONDS = int(
    os.getenv("BUSYBAR_TIMER_TOLERANCE_SECONDS", "90")
)


# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------

def log(message):
    print(
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}",
        flush=True,
    )


# ----------------------------------------------------------------------
# BUSY Bar connection
# ----------------------------------------------------------------------

def connect_busybar():
    log(f"Connecting to BUSY Bar at {BUSYBAR_IP}")

    kwargs = {}

    if BUSYBAR_TOKEN:
        kwargs["token"] = BUSYBAR_TOKEN

    bb = BusyBar(
        BUSYBAR_IP,
        **kwargs,
    )

    version = bb.version()

    log(
        "Connected to BUSY Bar. "
        f"API={version.api_semver or 'unknown'}"
    )

    return bb


# ----------------------------------------------------------------------
# Cloudflare status
# ----------------------------------------------------------------------

def get_cloudflare_status():
    response = requests.get(
        CLOUDFLARE_STATUS_URL,
        timeout=5,
        headers={
            "Cache-Control": "no-cache",
        },
    )

    response.raise_for_status()

    return response.json()


def parse_until(until):
    if not until:
        return None

    if until.endswith("Z"):
        until = until[:-1] + "+00:00"

    return datetime.fromisoformat(until)


def seconds_until(until):
    end = parse_until(until)

    if end is None:
        return 0

    now = datetime.now().astimezone()

    remaining = int(
        (end - now).total_seconds()
    )

    return max(0, remaining)


# ----------------------------------------------------------------------
# BUSY Bar profile helpers
# ----------------------------------------------------------------------

def get_profiles(bb):
    """
    Return the two profiles we use:

      busy   -> confirmed Outlook meeting
      custom -> tentative Outlook meeting
    """

    busy_profile = bb.busy_profile("busy")
    custom_profile = bb.busy_profile("custom")

    log(
        f"BUSY profile: "
        f"title='{busy_profile.title}', id='{busy_profile.id}'"
    )

    log(
        f"CUSTOM profile: "
        f"title='{custom_profile.title}', id='{custom_profile.id}'"
    )

    return busy_profile, custom_profile


# ----------------------------------------------------------------------
# BUSY Bar snapshot helpers
# ----------------------------------------------------------------------

def current_snapshot(bb):
    return bb.busy_snapshot()


def snapshot_description(snapshot):
    state = snapshot.snapshot

    if state.type == "NOT_STARTED":
        return "idle"

    if state.type == "SIMPLE":
        return (
            f"SIMPLE card={state.card_id}, "
            f"remaining={state.time_left_ms // 1000}s, "
            f"paused={state.is_paused}"
        )

    if state.type == "INFINITE":
        return (
            f"INFINITE card={state.card_id}, "
            f"paused={state.is_paused}"
        )

    return state.type


# ----------------------------------------------------------------------
# BUSY Bar state changes
# ----------------------------------------------------------------------

def set_idle(bb):
    log("Setting BUSY Bar -> IDLE")

    snapshot = types.BusySnapshot(
        snapshot=types.BusySnapshotNotStarted(
            type="NOT_STARTED"
        ),
        snapshot_timestamp_ms=int(time.time() * 1000),
    )

    result = bb.busy_snapshot_set(snapshot)

    log(f"Idle update result: {result}")


def set_timer(bb, profile, seconds, label):
    milliseconds = seconds * 1000

    log(
        f"Setting BUSY Bar -> {label} "
        f"for {seconds}s ({milliseconds} ms)"
    )

    snapshot = types.BusySnapshot(
        snapshot=types.BusySnapshotSimple(
            type="SIMPLE",
            card_id=profile.id,
            time_left_ms=milliseconds,
            is_paused=False,
        ),
        snapshot_timestamp_ms=int(time.time() * 1000),
    )

    result = bb.busy_snapshot_set(snapshot)

    log(f"{label} update result: {result}")


# ----------------------------------------------------------------------
# State comparison
# ----------------------------------------------------------------------

def timer_already_correct(
    snapshot,
    expected_profile_id,
    expected_seconds,
):
    state = snapshot.snapshot

    if state.type != "SIMPLE":
        return False

    if state.card_id != expected_profile_id:
        return False

    if state.is_paused:
        return False

    actual_seconds = state.time_left_ms // 1000

    difference = abs(
        actual_seconds - expected_seconds
    )

    log(
        f"Existing timer remaining={actual_seconds}s, "
        f"calendar expects={expected_seconds}s, "
        f"difference={difference}s"
    )

    return difference <= TIMER_TOLERANCE_SECONDS


# ----------------------------------------------------------------------
# Synchronization
# ----------------------------------------------------------------------

def synchronize(
    bb,
    busy_profile,
    custom_profile,
):
    cloud = get_cloudflare_status()

    status = cloud.get("status", "unknown")
    until = cloud.get("until")

    log(
        f"Calendar state={status}, "
        f"until={until}"
    )

    snapshot = current_snapshot(bb)

    log(
        "BUSY Bar currently: "
        + snapshot_description(snapshot)
    )

    # --------------------------------------------------------------
    # FREE / UNKNOWN
    # --------------------------------------------------------------

    if status in ("free", "unknown"):
        if snapshot.snapshot.type == "NOT_STARTED":
            log(
                "BUSY Bar already idle -- "
                "no update required."
            )
        else:
            set_idle(bb)

        return

    # --------------------------------------------------------------
    # Validate active state
    # --------------------------------------------------------------

    if status not in (
        "busy",
        "tentative",
    ):
        log(
            f"Unsupported calendar status: {status}"
        )
        return

    remaining = seconds_until(until)

    if remaining <= 0:
        log(
            "Meeting has expired -- "
            "setting BUSY Bar idle."
        )

        if snapshot.snapshot.type != "NOT_STARTED":
            set_idle(bb)

        return

    # --------------------------------------------------------------
    # Pick profile
    # --------------------------------------------------------------

    if status == "busy":
        profile = busy_profile
        label = "MEETING"

    else:
        profile = custom_profile
        label = "TENTATIVE"

    # --------------------------------------------------------------
    # Don't keep resetting the BUSY Bar timer.
    # --------------------------------------------------------------

    if timer_already_correct(
        snapshot,
        profile.id,
        remaining,
    ):
        log(
            f"{label} already programmed correctly -- "
            "leaving BUSY Bar timer alone."
        )
        return

    # --------------------------------------------------------------
    # Program new/changed meeting
    # --------------------------------------------------------------

    set_timer(
        bb,
        profile,
        remaining,
        label,
    )


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    if not CLOUDFLARE_STATUS_URL:
        print(
            "ERROR: CLOUDFLARE_STATUS_URL "
            "environment variable is required."
        )
        sys.exit(1)

    log(
        "Outlook -> Cloudflare -> "
        "BUSY Bar controller starting"
    )

    log(f"BUSY Bar IP: {BUSYBAR_IP}")
    log(f"Poll interval: {POLL_SECONDS}s")

    bb = None
    busy_profile = None
    custom_profile = None

    while True:
        try:
            if bb is None:
                bb = connect_busybar()

                busy_profile, custom_profile = (
                    get_profiles(bb)
                )

            synchronize(
                bb,
                busy_profile,
                custom_profile,
            )

        except KeyboardInterrupt:
            log("Stopping.")
            break

        except Exception as exc:
            log(
                f"ERROR: {type(exc).__name__}: "
                f"{exc}"
            )

            #
            # Force reconnect next cycle.
            #
            bb = None
            busy_profile = None
            custom_profile = None

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()