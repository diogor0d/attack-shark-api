# Attack Shark X68HE Lighting API

Windows-first research tooling and a localhost API for the wired Attack Shark X68HE
(`3151:502D`). The project exposes safe built-in lighting controls and keeps live per-key
streaming disabled because the tested keyboard's captured per-key path writes patterns to
flash.

## Safety status

- Device discovery and read-only probing are supported for internal device IDs `2270`,
  `2472`, and `2902`.
- Built-in lighting changes use the documented `SET_LEDPARAM` command only.
- Firmware, reset, calibration, flash erase, keymap, macro, Hall-effect settings, and
  flash-backed per-key uploads are outside the command allowlist.
- Live per-key frames remain disabled. The separate global-colour WebSocket uses only the
  capture-proven volatile mode 21 / opcode `0x0E` path, capped at 20 FPS. Custom per-key
  patterns use flash-backed opcode `0x0C` and remain blocked.
- The Attack Shark driver, Sharkfin, OpenRGB, and this service must not control the HID
  interface at the same time.

This is an independent interoperability project. It is not affiliated with Attack Shark,
ROYUAN, Sharkfin, or OpenRGB.

## Development setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\pytest.exe
```

Run a read-only probe:

```powershell
.\.venv\Scripts\x68ctl.exe probe
```

Start the localhost API:

```powershell
.\.venv\Scripts\x68ctl.exe serve
```

The service binds to `127.0.0.1:8768`. Interactive OpenAPI documentation is available at
`http://127.0.0.1:8768/docs`.

The connected revision exposes 66 physical keys. The model name is not the LED count, and
the API reports the discovered LED count and mapping rather than assuming 68.

Built-in preset example:

```powershell
Invoke-RestMethod -Method Put `
  -Uri http://127.0.0.1:8768/v1/devices/x68he/lighting/preset `
  -ContentType application/json `
  -Body '{"mode":"static","color":"#00ff80","brightness":4,"speed":0,"option":0}'
```

See [the capture guide](docs/capture-guide.md), [protocol notes](docs/protocol.md), and
[OpenRGB path](docs/openrgb.md) for the evidence and remaining work.

## Current limitation

Controlled USB captures on internal device ID `2902` established the strict capability
checkpoint:

- mode 21 streams one volatile RGB colour for the whole keyboard with opcode `0x0E`;
- Light Edit uploads a 126-slot per-key matrix with flash-backed opcode `0x0C`;
- mode 22 emits opcode `0x0D` at about 49 FPS, but the captured payload remained zero during
  a system-output test tone, so its signal fields and audio source are not yet established.

`/v1/devices/x68he/lighting/global-stream` accepts exactly one RGB triplet per binary or
JSON frame, retains only the newest queued frame, and restores the exact captured lighting
state when the connection closes. Device metadata advertises
`global_color_streaming=true`, `per_key_streaming=false`, and a 20 FPS ceiling. Existing
per-key frame and WebSocket endpoints continue to return an unsupported error. OpenRGB
per-key work remains gated because arbitrary volatile per-key frames have not been found.

Only one API process may run at a time; the Windows service path holds an OS-wide named
mutex. Only one stream may own the HID device, independently of that process guard.
