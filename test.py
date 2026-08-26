#!/usr/bin/env python3

import time
from busylib import BusyBar, types

bb = BusyBar("10.0.4.20")

DISPLAY_SECONDS = 15

profile = bb.busy_profile("busy")

print("Before:")
print(profile.model_dump_json(indent=2))

new_settings = profile.busy_bar_settings.model_copy(
    update={
        "theme": "meeting"
    }
)

new_timer = types.BusyTimerInfiniteSettings(
    type="INFINITE"
)

updated = profile.model_copy(
    update={
        "title": "meeting",
        "busy_bar_settings": new_settings,
        "timer_settings": new_timer,
    }
)

print("\nSending:")
print(updated.model_dump_json(indent=2))

print("\nUpdating profile...")
print(
    bb.busy_profile_set(
        "busy",
        updated
    )
)

time.sleep(2)

profile = bb.busy_profile("busy")

print("\nRead-back:")
print(profile.model_dump_json(indent=2))

print("\nStarting display...")

snapshot = types.BusySnapshot(
    snapshot=types.BusySnapshotInfinite(
        type="INFINITE",
        card_id=profile.id,
        is_paused=False,
    ),
    snapshot_timestamp_ms=int(
        time.time() * 1000
    ),
)

print(
    bb.busy_snapshot_set(snapshot)
)

time.sleep(DISPLAY_SECONDS)

print("\nReturning to idle...")

idle = types.BusySnapshot(
    snapshot=types.BusySnapshotNotStarted(
        type="NOT_STARTED"
    ),
    snapshot_timestamp_ms=int(
        time.time() * 1000
    ),
)

print(
    bb.busy_snapshot_set(idle)
)