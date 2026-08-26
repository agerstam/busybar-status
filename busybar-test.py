#!/usr/bin/env python3

import time
import requests

BASE = "http://10.0.4.20"

# Read current BUSY profile
r = requests.get(
    f"{BASE}/api/busy/profiles/busy",
    timeout=5
)
r.raise_for_status()

profile = r.json()

print("BEFORE:")
print(profile)

# Change the profile
profile["title"] = "MEETING"
profile["busy_bar_settings"]["theme"] = "meeting"

profile["timer_settings"] = {
    "type": "INFINITE"
}

# THIS is the important part
profile["profile_timestamp_ms"] = int(time.time() * 1000)

print("\nSENDING:")
print(profile)

r = requests.put(
    f"{BASE}/api/busy/profiles/busy",
    json=profile,
    timeout=5
)

print("\nPUT:")
print(r.status_code, r.text)

time.sleep(1)

# Read it back
r = requests.get(
    f"{BASE}/api/busy/profiles/busy",
    timeout=5
)
r.raise_for_status()

print("\nAFTER:")
print(r.json())