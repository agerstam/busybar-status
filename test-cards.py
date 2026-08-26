#!/usr/bin/env python3

import os
import time

from busylib import BusyBar, types


BUSYBAR_IP = os.getenv("BUSYBAR_IP", "10.0.4.20")

TEST_SECONDS = 10
SETTLE_SECONDS = 3


def set_theme(bb, slot, theme):
    print(f"\nReading profile '{slot}'...")

    profile = bb.busy_profile(slot)

    print(
        f"Current: title={profile.title}, "
        f"theme={profile.busy_bar_settings.theme}"
    )

    if profile.busy_bar_settings.theme != theme:
        print(f"Changing theme -> {theme}")

        profile.busy_bar_settings.theme = theme

        result = bb.busy_profile_set(
            slot,
            profile,
        )

        print("Profile update result:", result)

        print(
            f"Waiting {SETTLE_SECONDS}s "
            "for BUSY Bar to apply profile..."
        )

        time.sleep(SETTLE_SECONDS)

    # IMPORTANT: re-read from device
    profile = bb.busy_profile(slot)

    print(
        f"Verified: title={profile.title}, "
        f"theme={profile.busy_bar_settings.theme}"
    )

    return profile


def start_timer(bb, profile):
    snapshot = types.BusySnapshot(
        snapshot=types.BusySnapshotSimple(
            type="SIMPLE",
            card_id=profile.id,
            time_left_ms=TEST_SECONDS * 1000,
            is_paused=False,
        ),
        snapshot_timestamp_ms=int(
            time.time() * 1000
        ),
    )

    print(
        f"Starting {TEST_SECONDS}s timer "
        f"using card_id={profile.id}"
    )

    result = bb.busy_snapshot_set(snapshot)

    print("Timer result:", result)


def set_idle(bb):
    snapshot = types.BusySnapshot(
        snapshot=types.BusySnapshotNotStarted(
            type="NOT_STARTED",
        ),
        snapshot_timestamp_ms=int(
            time.time() * 1000
        ),
    )

    print("Returning BUSY Bar to idle...")

    print(
        bb.busy_snapshot_set(snapshot)
    )


bb = BusyBar(BUSYBAR_IP)

print(f"BUSY Bar: {BUSYBAR_IP}")

#
# Change ONLY this line between tests.
#
SLOT = "busy"
THEME = "meeting"

try:
    profile = set_theme(
        bb,
        SLOT,
        THEME,
    )

    start_timer(
        bb,
        profile,
    )

    print(
        "\nWatch BUSY Bar now..."
    )

    time.sleep(TEST_SECONDS + 2)

finally:
    try:
        set_idle(bb)
    except Exception as exc:
        print(
            "WARNING: Could not return to idle:",
            exc,
        )