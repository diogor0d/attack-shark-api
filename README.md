# Attack Shark X68HE Lighting API

Windows-first research tooling and a localhost API for the wired Attack Shark X68HE
(`3151:502D`). The project exposes built-in effects, volatile whole-keyboard colour, and
guarded static per-key patterns. Live per-key streaming remains disabled because the tested
keyboard's only per-key path stores patterns in flash.

## Safety status

- Device discovery and read-only probing are supported for internal device IDs `2270`,
  `2472`, and `2902`.
- Built-in lighting changes use the documented `SET_LEDPARAM` command only.
- Firmware, reset, calibration, flash erase, keymap, macro, and Hall-effect settings are
  outside the command allowlist.
- Live per-key frames remain disabled. The separate global-colour WebSocket uses only the
  capture-proven volatile mode 21 / opcode `0x0E` path, capped at 20 FPS.
- Static per-key patterns use USERPIC slot 0 in flash. Each write requires explicit
  confirmation, identical patterns are not rewritten, and different writes are limited to
  one every ten minutes.
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

Set a persistent per-key pattern from the CLI. This example assigns one colour to each
physical row. `--key NAME=#RRGGBB` can be repeated and overrides a row colour:

```powershell
.\.venv\Scripts\x68ctl.exe set-custom `
  --row 0=#ff0000 --row 1=#00ff00 --row 2=#0000ff `
  --row 3=#ff00ff --row 4=#ffffff `
  --confirm-flash-write
```

The equivalent REST endpoint accepts key names from the device's `led_map`:

```powershell
$body = @{
  colors = @{ escape = '#ff0000'; a = '#00ff00'; space = '#0000ff' }
  background = '#000000'
  confirm_flash_write = $true
} | ConvertTo-Json

Invoke-RestMethod -Method Put `
  -Uri http://127.0.0.1:8768/v1/devices/x68he/lighting/custom `
  -ContentType application/json `
  -Body $body
```

This operation overwrites the keyboard's USERPIC slot 0 and leaves lighting mode 13
selected. It is intended for occasional static changes, not animation.

Run a bounded whole-keyboard hue cycle. The command uses only volatile mode 21 / opcode
`0x0E` and restores the exact lighting state it captured before the demo:

```powershell
.\.venv\Scripts\x68ctl.exe demo --fps 20 --duration 10
```

For physical research on music mode, close Attack Shark Driver and any running API server,
then replay the four sanitized spectrum bodies captured from 110, 220, 440, and 880 Hz.
The probe accepts only the observed 32-bin value range `0..6`, runs at no more than 20 FPS, and
restores the previous lighting state:

```powershell
.\.venv\Scripts\python.exe tools\replay_spectrum_probe.py
```

This probe tests the firmware's built-in spectrum renderer. It does not provide per-key RGB
addressing and is intentionally not exposed through REST or WebSocket.

For physical mapping, use interactive mode so the active label remains visible in the same
PowerShell window. Press Enter only after comparing that pattern with the keyboard; press
`Q` at any time to restore the previous lighting and exit:

```powershell
.\.venv\Scripts\python.exe tools\replay_spectrum_probe.py `
  --bands 0,5,10,15,20,25,28 `
  --interactive
```

For a WebSocket soak test, start `x68ctl serve` in one terminal and run this in another:

```powershell
.\.venv\Scripts\python.exe tools\soak_global_stream.py --fps 20 --duration 900
```

See [the capture guide](docs/capture-guide.md), [protocol notes](docs/protocol.md), and
[OpenRGB path](docs/openrgb.md) for the evidence and remaining work.

## Current limitation

Controlled USB captures on internal device ID `2902` established the strict capability
checkpoint:

- mode 21 streams one volatile RGB colour for the whole keyboard with opcode `0x0E`;
- Light Edit uploads a 126-slot per-key matrix with flash-backed opcode `0x0C`. The complete
  66-key map and a five-row RGB pattern were verified on the connected `2902` revision;
- mode 22 emits opcode `0x0D` at about 49 FPS. The controlled 2026-09-20 capture contained
  8,979 reports with a volatile 32-byte body in bytes 8-39; values ranged from 0..6 and
  controlled 110/220/440/880 Hz tones peaked at bins 2/5/9/19 respectively. This identifies
  a firmware spectrum representation. Repeated physical replay rendered irregular diagonal
  key groups for lower bins, while the 880 Hz profile produced no visible lighting.

`/v1/devices/x68he/lighting/global-stream` accepts exactly one RGB triplet per binary or
JSON frame, retains only the newest queued frame, and restores the exact captured lighting
state when the connection closes. Device metadata advertises
`global_color_streaming=true`, `per_key_streaming=false`, and a 20 FPS ceiling. Existing
per-key frame and WebSocket endpoints continue to return an unsupported error. Metadata also
advertises `static_per_key=true`; the guarded `/lighting/custom` endpoint performs one
persistent upload. OpenRGB direct/per-LED work remains gated because arbitrary volatile
per-key frames have not been found. Opcode `0x0D` is retained only as a guarded research
probe; it is not suitable for direct LED control.

Only one API process may run at a time; the Windows service path holds an OS-wide named
mutex. Only one stream may own the HID device, independently of that process guard.
