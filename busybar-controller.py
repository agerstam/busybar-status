#!/usr/bin/env python3
"""Local BUSY Bar controller and web interface."""
import argparse, base64, ipaddress, json, os, re, struct, sys, threading, time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import requests

STATUS_URL = "https://busybar-status.matsagerstam.workers.dev/status"
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
DATA_DIR = (Path.home() / "Library/Application Support/BusyBarStatus"
            if getattr(sys, "frozen", False) else Path(__file__).parent)
PREVIEW_DIR = DATA_DIR / ".preview-cache"
DEFAULTS = {"work_sync_enabled": True, "device_ip": "10.0.4.20",
            "poll_interval_seconds": 30, "sound_enabled": True, "sound_volume": 50,
            "state_cards": {"busy": "theme:meeting", "tentative": "theme:booked", "ooo": "theme:keep_out"}}
SLOTS = {"busy", "custom"}

def log(message):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}", flush=True)

def parse_until(value):
    if not isinstance(value, str) or not value.strip(): return None
    try:
        result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        # Outlook's Cloudflare payload currently sends `until` in local wall
        # time without an offset. Treat a naive value as this controller's local
        # timezone; treating it as UTC makes Pacific events expire hours early.
        if result.tzinfo is None:
            result = result.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return result.astimezone(timezone.utc)
    except ValueError: return None

class Config:
    def __init__(self, path):
        self.path, self.lock = path, threading.RLock()
        saved = {}
        if path.exists():
            try: saved = json.loads(path.read_text())
            except (OSError, ValueError) as exc: log(f"Ignoring invalid config: {exc}")
        if not isinstance(saved, dict):
            log("Ignoring invalid config: expected a JSON object")
            saved = {}
        merged = {**DEFAULTS, **saved}
        saved_cards = saved.get("state_cards", {})
        if not isinstance(saved_cards, dict):
            log("Ignoring invalid state_cards config")
            saved_cards = {}
        merged["state_cards"] = {**DEFAULTS["state_cards"], **saved_cards}
        self.value = self.validate(merged)

    @staticmethod
    def validate(c):
        ipaddress.ip_address(str(c["device_ip"])); interval = int(c["poll_interval_seconds"])
        if not 5 <= interval <= 3600: raise ValueError("Poll interval must be 5–3600 seconds")
        mappings = c["state_cards"]
        # Migrate configuration written by the first UI prototype.
        legacy = {"busy": "theme:meeting", "custom": "theme:booked"}
        mappings = {s: legacy.get(mappings.get(s), mappings.get(s)) for s in ("busy", "tentative", "ooo")}
        if any(not isinstance(mappings[s], str) or not mappings[s].startswith(("theme:", "custom:")) for s in mappings):
            raise ValueError("Invalid state card")
        volume = int(c.get("sound_volume", 50))
        if not 1 <= volume <= 100: raise ValueError("Saved sound volume must be 1–100")
        return {"work_sync_enabled": bool(c["work_sync_enabled"]), "device_ip": str(c["device_ip"]),
                "poll_interval_seconds": interval,
                "sound_enabled": bool(c.get("sound_enabled", True)), "sound_volume": volume,
                "state_cards": {s: mappings[s] for s in ("busy", "tentative", "ooo")}}

    def get(self):
        with self.lock: return json.loads(json.dumps(self.value))

    def update(self, changes):
        with self.lock:
            candidate = self.get()
            for key in ("work_sync_enabled", "device_ip", "poll_interval_seconds", "sound_enabled", "sound_volume"):
                if key in changes: candidate[key] = changes[key]
            if "state_cards" in changes: candidate["state_cards"].update(changes["state_cards"])
            self.value = self.validate(candidate)
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps(self.value, indent=2) + "\n"); temp.replace(self.path)
            return self.get()

class Device:
    def __init__(self, ip):
        self.url, self.session = f"http://{ip}", requests.Session()
        if os.getenv("BUSYBAR_API_TOKEN"): self.session.headers["X-API-Token"] = os.environ["BUSYBAR_API_TOKEN"]

    def request(self, method, path, **kwargs):
        r = self.session.request(method, self.url + path, timeout=5, **kwargs); r.raise_for_status(); return r

    def profile(self, slot):
        if slot not in SLOTS: raise ValueError("Unknown card")
        return self.request("GET", f"/api/busy/profiles/{slot}").json()

    def listing(self, path): return self.request("GET", "/api/storage/list", params={"path": path}).json()["list"]

    def cards(self):
        themes = [x["name"] for x in self.listing("/ext/apps_assets/busy/themes") if x["type"] == "dir"]
        custom = [x["name"] for x in self.listing("/ext/user_assets/draw_tool")
                  if x["type"] == "file" and x["name"].lower().endswith(".png") and x["name"] != "temp.png"]
        labels = {"dnd": "Do Not Disturb"}
        return ([{"id": f"theme:{name}", "kind": "theme", "name": labels.get(name, name.replace("_", " ").title()),
                  "preview": f"/api/app/theme-preview?name={name}" if (PREVIEW_DIR / f"{name}.bmp").exists() else None}
                 for name in themes] +
                [{"id": f"custom:{name}", "kind": "custom", "name": name,
                  "preview": "/api/app/asset?name=" + name} for name in custom])

    def display(self, card, seconds=None):
        self.clear_draws()
        if card.startswith("custom:"):
            # Canvas cannot preempt a running BUSY snapshot on firmware 1.1.1,
            # even at the documented maximum priority.
            self.stop_busy()
            name = card.removeprefix("custom:")
            available = {x["name"] for x in self.listing("/ext/user_assets/draw_tool") if x["type"] == "file"}
            if name not in available or not name.lower().endswith(".png"): raise ValueError("Unknown custom image")
            timeout = seconds or 0
            self.request("POST", "/api/display/draw", json={"application_name": "draw_tool", "priority": 100,
                "elements": [{"id": "busybar_status", "type": "image", "path": name,
                              "x": 0, "y": 0, "display": "front", "timeout": timeout}]})
            return
        if not card.startswith("theme:"): raise ValueError("Unknown card")
        theme = card.removeprefix("theme:")
        if theme not in {x["name"] for x in self.listing("/ext/apps_assets/busy/themes") if x["type"] == "dir"}:
            raise ValueError("Unknown device theme")
        p = self.profile("busy")
        if seconds is None: snapshot = {"type": "INFINITE", "card_id": p["id"], "is_paused": False}
        else:
            if not 1 <= seconds <= 86400: raise ValueError("Duration must be 1 second–24 hours")
            snapshot = {"type": "SIMPLE", "card_id": p["id"], "time_left_ms": seconds * 1000, "is_paused": False}
        snapshot["busy_bar_settings"] = {**p["busy_bar_settings"], "theme": theme}
        self.request("PUT", "/api/busy/snapshot", json={"snapshot": snapshot, "snapshot_timestamp_ms": int(time.time()*1000)})

    @staticmethod
    def color(value):
        if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value): raise ValueError("Invalid color")
        return value.upper() + "FF"

    def display_text(self, text, foreground, background):
        if not isinstance(text, str) or not text or len(text) > 120 or any(ord(c) < 32 or ord(c) > 126 for c in text):
            raise ValueError("Running text must be 1–120 printable ASCII characters; emoji are not supported")
        self.clear_draws()
        self.stop_busy()
        self.request("POST", "/api/display/draw", json={"application_name": "busybar_status", "priority": 100,
            "elements": [
                {"id": "background", "type": "rectangle", "x": 0, "y": 0, "width": 72, "height": 16,
                 "fill": "solid", "fill_colors": [self.color(background)], "border_width": 0, "display": "front", "timeout": 0},
                {"id": "message", "type": "text", "text": text, "font": "normal", "color": self.color(foreground),
                 "x": 0, "y": 8, "align": "mid_left", "width": 72, "scroll_rate": 600,
                 "scroll_start_delay": 500, "scroll_repeat_delay": 1000, "display": "front", "timeout": 0}
            ]})

    def clear_draws(self):
        for app in ("draw_tool", "busybar_status"):
            self.request("DELETE", "/api/display/draw", params={"application_name": app})

    def stop_busy(self):
        current = self.request("GET", "/api/busy/snapshot").json()
        settings = current.get("snapshot", {}).get("busy_bar_settings")
        if not settings:
            settings = self.profile("busy")["busy_bar_settings"]
        self.request("PUT", "/api/busy/snapshot", json={
            "snapshot": {"type": "NOT_STARTED", "busy_bar_settings": settings},
            "snapshot_timestamp_ms": int(time.time() * 1000),
        })

    def stop(self):
        self.clear_draws()
        self.stop_busy()
    def volume(self): return int(self.request("GET", "/api/audio/volume").json()["volume"])
    def set_volume(self, volume): self.request("POST", "/api/audio/volume", params={"volume": volume, "silent": 1})
    def info(self):
        status = self.request("GET", "/api/status").json()
        return {
            "api_version": status.get("system", {}).get("api_semver"),
            "firmware_version": status.get("firmware", {}).get("version"),
            "firmware_build": status.get("firmware", {}).get("build_date"),
            "serial_number": status.get("device", {}).get("serial_number"),
            "uptime": status.get("system", {}).get("uptime"),
            "battery_charge": status.get("power", {}).get("battery_charge"),
            "power_state": status.get("power", {}).get("state"),
            "transport": self.request("GET", "/api/transport").json().get("type"),
        }
    def asset(self, name):
        available = {x["name"] for x in self.listing("/ext/user_assets/draw_tool") if x["type"] == "file"}
        if name not in available or not name.lower().endswith(".png"): raise ValueError("Unknown custom image")
        return self.request("GET", "/api/storage/read", params={"path": "/ext/user_assets/draw_tool/" + name}).content
    def screen(self, display):
        raw = base64.b64decode(self.request("GET", "/api/screen", params={"display": display}).content)
        width, height = 72, 16
        if len(raw) != width * height * 3: raise ValueError("Unexpected screen frame size")
        # API v25 returns base64 RGB888 pixels despite declaring image/bmp.
        rows = [raw[y*width*3:(y+1)*width*3] for y in range(height)]
        pixels = b"".join(
            bytes((row[i+2], row[i+1], row[i]))
            for row in reversed(rows) for i in range(0, len(row), 3)
        )
        return (b"BM" + struct.pack("<IHHI", 54+len(pixels), 0, 0, 54) +
                struct.pack("<IIIHHIIIIII", 40, width, height, 1, 24, 0, len(pixels), 2835, 2835, 0, 0) + pixels)

class Controller:
    def __init__(self, config):
        self.config, self.lock, self.wake = config, threading.RLock(), threading.Event()
        self.runtime = {"cloud_status": None, "cloud_until": None, "cloud_updated": None, "displayed_slot": None,
                        "manual_ends_at": None, "last_poll_at": None, "last_error": None}
        self.force, self.manual_timer, self.manual_generation = True, None, 0

    def device(self): return Device(self.config.get()["device_ip"])
    def state(self):
        with self.lock: result = {"config": self.config.get(), "runtime": self.runtime.copy()}
        try: result.update(cards=self.device().cards(), device_volume=self.device().volume(), device_error=None)
        except Exception as exc: result.update(cards=[], device_error=str(exc))
        return result

    def update(self, changes):
        old = self.config.get()
        if "sound_enabled" in changes and bool(changes["sound_enabled"]) != old["sound_enabled"]:
            device = Device(str(changes.get("device_ip", old["device_ip"])))
            enabled = bool(changes["sound_enabled"])
            current = device.volume()
            if not enabled and current > 0: changes = {**changes, "sound_volume": current}
            device.set_volume(int(changes.get("sound_volume", old["sound_volume"])) if enabled else 0)
        new = self.config.update(changes)
        with self.lock:
            if old["device_ip"] != new["device_ip"] or old["state_cards"] != new["state_cards"] or not old["work_sync_enabled"]: self.force = True
            if old["work_sync_enabled"] and not new["work_sync_enabled"]: self.runtime.update(cloud_status=None, cloud_until=None)
            if not old["work_sync_enabled"] and new["work_sync_enabled"]: self._cancel_manual_locked()
        self.wake.set(); return new

    def _cancel_manual_locked(self):
        self.manual_generation += 1
        if self.manual_timer: self.manual_timer.cancel()
        self.manual_timer = None
        self.runtime["manual_ends_at"] = None

    def manual(self, card, seconds, text=None, foreground="#FFFFFF", background="#000000"):
        if self.config.get()["work_sync_enabled"]: raise PermissionError("Turn work sync off first")
        # Manual durations are managed here so sound behavior is identical for
        # native themes and Draw Tool images and never changes global volume.
        if text: self.device().display_text(text, foreground, background); card = "text"
        else: self.device().display(card, seconds)
        with self.lock:
            self._cancel_manual_locked()
            generation = self.manual_generation
            ends = datetime.now(timezone.utc).timestamp() + seconds if seconds else None
            self.runtime.update(displayed_slot=card, manual_ends_at=datetime.fromtimestamp(ends, timezone.utc).isoformat() if ends else None, last_error=None)
            if seconds:
                self.manual_timer = threading.Timer(seconds, self._finish_manual, args=(generation,))
                self.manual_timer.daemon = True
                self.manual_timer.start()

    def _finish_manual(self, generation):
        with self.lock:
            if generation != self.manual_generation or self.config.get()["work_sync_enabled"]: return
            self.manual_timer = None
        try:
            self.device().stop()
            with self.lock: self.runtime.update(displayed_slot=None, manual_ends_at=None, last_error=None)
        except Exception as exc:
            with self.lock: self.runtime.update(manual_ends_at=None, last_error=str(exc))
            log(f"Manual timer completion error: {exc}")

    def stop(self):
        if self.config.get()["work_sync_enabled"]: raise PermissionError("Turn work sync off first")
        with self.lock: self._cancel_manual_locked()
        self.device().stop()
        with self.lock: self.runtime.update(displayed_slot=None, last_error=None)

    def force_sync(self):
        if not self.config.get()["work_sync_enabled"]:
            raise PermissionError("Turn auto refresh on before forcing synchronization")
        with self.lock: self.force = True
        self.poll()

    def capture_previews(self):
        if self.config.get()["work_sync_enabled"]:
            raise PermissionError("Turn work sync off before capturing theme previews")
        device = self.device()
        themes = [c for c in device.cards() if c["kind"] == "theme"]
        PREVIEW_DIR.mkdir(exist_ok=True)
        try:
            for index, card in enumerate(themes, 1):
                log(f"Capturing theme preview {index}/{len(themes)}: {card['name']}")
                device.display(card["id"], 2)
                time.sleep(.45)
                (PREVIEW_DIR / f"{card['id'].removeprefix('theme:')}.bmp").write_bytes(device.screen(0))
        finally:
            device.stop()
        return len(themes)

    def poll(self):
        r = requests.get(STATUS_URL, headers={"Cache-Control":"no-cache"}, timeout=10); r.raise_for_status(); data=r.json()
        status = str(data.get("status", "free")).strip().lower().replace("idle", "free")
        if status not in {"free", "busy", "tentative", "ooo"}: status = "free"
        until = parse_until(data.get("until"))
        if status != "free" and until and until <= datetime.now(timezone.utc): status = "free"
        with self.lock: changed = status != self.runtime["cloud_status"] or self.force
        if changed:
            if status == "free": self.device().stop(); slot = None
            else: slot = self.config.get()["state_cards"][status]; self.device().display(slot)
            with self.lock: self.runtime["displayed_slot"], self.force = slot, False
            log(f"Applied {status}: {slot or 'display off'}")
        with self.lock: self.runtime.update(cloud_status=status, cloud_until=until.isoformat() if until else None,
                                           cloud_updated=data.get("updated"),
                                           last_poll_at=datetime.now(timezone.utc).isoformat(), last_error=None)

    def run(self):
        while True:
            c = self.config.get()
            if c["work_sync_enabled"]:
                try: self.poll()
                except Exception as exc:
                    with self.lock: self.runtime.update(last_error=str(exc), last_poll_at=datetime.now(timezone.utc).isoformat())
                    log(f"Sync error: {exc}")
            self.wake.wait(c["poll_interval_seconds"]); self.wake.clear()

class Handler(BaseHTTPRequestHandler):
    controller, web = None, None
    max_body_bytes = 64 * 1024
    def log_message(self, fmt, *args): log("Web: " + fmt % args)
    def send_json(self, code, value):
        body=json.dumps(value).encode(); self.send_response(code); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length < 0 or length > self.max_body_bytes: raise ValueError("Request body is too large")
        return json.loads(self.rfile.read(length) or b"{}")
    def do_GET(self):
        p=urlparse(self.path)
        try:
            if p.path == "/":
                body=(self.web/"index.html").read_bytes(); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
            elif p.path == "/api/app/state": self.send_json(200,self.controller.state())
            elif p.path == "/api/app/about": self.send_json(200,self.controller.device().info())
            elif p.path == "/api/app/screen":
                body=self.controller.device().screen(int(parse_qs(p.query).get("display",[0])[0])); self.send_response(200); self.send_header("Content-Type","image/bmp"); self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
            elif p.path == "/api/app/asset":
                body=self.controller.device().asset(parse_qs(p.query).get("name",[""])[0]); self.send_response(200); self.send_header("Content-Type","image/png"); self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
            elif p.path == "/api/app/theme-preview":
                name=parse_qs(p.query).get("name",[""])[0]
                if not name.replace("_","").isalnum(): raise ValueError("Invalid theme name")
                body=(PREVIEW_DIR/f"{name}.bmp").read_bytes(); self.send_response(200); self.send_header("Content-Type","image/bmp"); self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
            else: self.send_json(404,{"error":"Not found"})
        except Exception as exc: self.send_json(502,{"error":str(exc)})
    def do_PUT(self):
        try:
            if self.path != "/api/app/config": return self.send_json(404,{"error":"Not found"})
            self.send_json(200,{"config":self.controller.update(self.body())})
        except Exception as exc: self.send_json(400,{"error":str(exc)})
    def do_POST(self):
        try:
            if self.path == "/api/app/manual":
                b=self.body(); seconds=b.get("duration_seconds"); self.controller.manual(str(b.get("slot","")),int(seconds) if seconds not in (None,"") else None,b.get("text"),b.get("foreground","#FFFFFF"),b.get("background","#000000"))
            elif self.path == "/api/app/stop": self.controller.stop()
            elif self.path == "/api/app/capture-previews": self.controller.capture_previews()
            elif self.path == "/api/app/sync": self.controller.force_sync()
            else: return self.send_json(404,{"error":"Not found"})
            self.send_json(200,{"ok":True})
        except PermissionError as exc: self.send_json(409,{"error":str(exc)})
        except Exception as exc: self.send_json(400,{"error":str(exc)})

def main():
    p=argparse.ArgumentParser(); p.add_argument("--host",default="127.0.0.1"); p.add_argument("--port",type=int,default=8765); p.add_argument("--config",type=Path,default=DATA_DIR/"config.json"); a=p.parse_args()
    a.config.parent.mkdir(parents=True,exist_ok=True)
    controller=Controller(Config(a.config)); Handler.controller=controller; Handler.web=RESOURCE_DIR/"web"
    threading.Thread(target=controller.run,daemon=True).start(); server=ThreadingHTTPServer((a.host,a.port),Handler)
    log(f"Web interface: http://{a.host}:{a.port}")
    try: server.serve_forever()
    except KeyboardInterrupt: log("Controller stopped")
    finally: server.server_close()

if __name__ == "__main__": main()
