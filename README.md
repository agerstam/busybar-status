# BUSY Bar status

Local web controller for mirroring Outlook availability from Cloudflare to a BUSY Bar.

## Install on macOS

Install it as a per-user background service:

```bash
make install
```

The installer builds a standalone `~/Applications/BUSY Bar Status.app`, starts the
controller, registers it to start whenever you log in, and opens
<http://127.0.0.1:8765>. No terminal needs to remain open. Logs are written to
`~/Library/Logs/BusyBarStatus`; settings and preview caches live in
`~/Library/Application Support/BusyBarStatus`.

To stop it and remove it from login startup while preserving settings and logs:

```bash
make uninstall
```

Run the installer again after moving the project directory because the LaunchAgent
stores its absolute path.

On first installation, allow **BUSY Bar Status** to access the local network when
macOS asks. You can change this later under **System Settings → Privacy & Security
→ Local Network**.

## Run for development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python busybar-controller.py
```

Open <http://127.0.0.1:8765>. Settings persist in the ignored `config.json`. The UI
enumerates all built-in themes and saved Draw Tool images, supports state-to-card
mappings, previews custom images, and permits manual card display only while work
synchronization is off.

Device sound can be globally enabled or muted from Device settings. Muting stores
the current non-zero volume so enabling sound restores it.

Manual mode also supports scrolling text with foreground and background colors.
The device API accepts 1–120 printable ASCII characters; its bitmap font does not
support emoji or other Unicode characters.

Built-in themes use a device-native animation format. With work sync off, use
**Capture real theme previews** once to render each theme on the device and cache
accurate thumbnails locally.

Set `BUSYBAR_API_TOKEN` if the device requires an API key.
