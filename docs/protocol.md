# X68HE protocol notes

Status date: 2026-09-20

Evidence labels used below:

- **LOCAL**: observed in the installed Attack Shark Driver v4 3.1.12 or Windows device data.
- **CAPTURED**: observed in a controlled USBPcap capture from the connected keyboard.
- **UPSTREAM**: documented by the independent Sharkfin protocol research.
- **HARDWARE VERIFIED**: sent by this implementation and confirmed visually on the physical
  keyboard.
- **CAPTURE NEEDED**: not yet confirmed against this physical keyboard.

## Identity and transport

| Property | Value | Evidence |
| --- | --- | --- |
| USB ID | `3151:502D` | LOCAL |
| Vendor HID interface | interface 2, usage page `0xFFFF`, usage `2` | LOCAL, UPSTREAM, CAPTURED |
| Feature report | ID 0, 64 bytes | UPSTREAM |
| Internal device IDs | `2270`, `2472`, `2902` | LOCAL, UPSTREAM |
| Protocol family | gen2 | LOCAL, UPSTREAM |
| Connected internal ID | `2902` | LOCAL read-only probe, 2026-09-08 |
| Connected firmware revision | `0` | LOCAL read-only probe, 2026-09-08 |
| Connected physical layout | 66 keys, vendor `Common66_X68` | LOCAL |

The internal ID must be read with `GET_IDENTIFY 0x8F`; the shared USB ID is insufficient
for selecting a writable protocol. Unknown internal IDs are read-only.

## Checksums and safe lighting packets

`Bit7` stores `0xFF - (sum(bytes[0:7]) & 0xFF)` at byte 7.

`Bit8` stores `0xFF - (sum(bytes[0:8]) & 0xFF)` at byte 8. `SET_LEDPARAM`
uses this checksum and keeps the complete RGB triplet in bytes 5-7; it does not also
store `Bit7` at byte 7.

Known read commands:

| Command | Opcode | Reply |
| --- | --- | --- |
| Identify | `0x8F` | internal ID as little-endian `u32` at bytes 1–4 |
| Revision | `0x80` | minor at byte 1, major at byte 2 |
| Lighting state | `0x87` | mode and parameters following the lighting layout |

The only public device write is `SET_LEDPARAM 0x07`, using `Bit8`:

```text
[0x07, mode, speed, brightness, (option << 4) | flags, R, G, B, checksum]
```

The package exposes the capture-derived whole-keyboard opcode `0x0E` only through the
bounded global-colour WebSocket. It exposes `0x0C` only through the guarded static-pattern
operation described below. Sending arbitrary raw reports is not part of the package
interface, and volatile per-key endpoints remain unsupported.

### Sanitized vendor-driver capture

A USBPcap session on 2026-09-08 captured only device address 4 on `USBPcap2`, the
connected `3151:502D` device. Attack Driver v4 sent 64-byte HID feature reports to
interface 2 in the host-to-device direction. The following nine-byte prefixes were
observed; the remainder of each report was zero-filled:

| Controlled action | Report prefix |
| --- | --- |
| Static red | `07 01 04 04 07 FF 00 00 E9` |
| Static green | `07 01 04 04 07 00 FF 00 E9` |
| Static blue | `07 01 04 04 07 00 00 FF E9` |
| Brightness off, existing near-white colour | `07 01 04 00 07 FA FF FA F9` |
| Restore brightness, existing near-white colour | `07 01 04 04 07 FA FF FA F5` |

This capture corrected an earlier encoder error that wrote `Bit7` over the blue channel.
The test fixtures now compare these prefixes byte-for-byte.

A controlled hardware smoke test on 2026-09-08 selected a static blue preset for one second
and restored the previously read mode `4` and RGB value `(255,255,255)`. Identification,
write allowlisting, and restoration all completed without a HID error. This verifies preset
control only; it is not evidence for live per-key streaming.

## Volatile whole-keyboard colour

A controlled mode-21 capture on 2026-09-08 first observed this normal mode-selection
packet:

```text
07 15 04 04 00 FA FF FA E8
```

The local helper then sent host-to-device 64-byte feature reports whose eight-byte prefix is:

```text
[0x0E, R, G, B, 0x00, 0x00, 0x00, Bit7]
```

Deterministic full-screen patches produced the following exact prefixes:

| Screen patch | Report prefix |
| --- | --- |
| Red | `0E FF 00 00 00 00 00 F2` |
| Green | `0E 00 FF 00 00 00 00 F2` |
| Blue | `0E 00 00 FF 00 00 00 F2` |
| White | `0E FF FF FF 00 00 00 F4` |
| Black | `0E 00 00 00 00 00 F1` |

The helper emitted unchanged-colour bursts at approximately 30 FPS and later screen
sampling at approximately 15-16 FPS. The capture contained 1,151 `0x0E` reports without a
prohibited opcode or recorded USB error. This is evidence for volatile, whole-keyboard RGB
only. The report contains one RGB triplet and cannot address individual LEDs.

## Live per-key status

The installed driver declares per-key patterns, host-driven screen mode `21`, and music mode
`22`. Mode 21 is capture-verified as global colour only. The volatile per-key format, if one
exists, remains **CAPTURE NEEDED**.

`SET_USERPIC 0x0C` is not a live-frame mechanism. Published research says its final page
commits RGB patterns to flash and that repeated uploads can stall some related controllers.
The implementation permits one strictly shaped seven-page upload for an explicitly
confirmed static change. It blocks this command from frame and WebSocket paths, suppresses
identical rewrites, and enforces a persistent ten-minute interval between different writes.

A controlled Light Edit capture on 2026-09-08 confirms that this X68HE revision uses
`0x0C` for per-key patterns. Selecting the custom pattern sent mode `13`, followed by seven
host-to-device `0x0C` pages. Restoring normal lighting sent another seven all-zero pages.
One upload has this observed layout:

```text
byte 0      0x0C
bytes 1-2  0x00, 0xFF
byte 3      page index 0..6
byte 4      data length: 56 for pages 0..5, 42 for page 6
byte 5      0 for pages 0..5, 1 for the final page
byte 6      0x00
byte 7      Bit7 checksum
bytes 8..   RGB matrix data
```

The pages contain 378 bytes, exactly 126 RGB slots. A single sparse capture mapped four
physical keys without additional writes:

| Key | Firmware matrix slot | Captured RGB |
| --- | ---: | --- |
| Escape | 1 | `FF 00 00` |
| A | 9 | `00 FF 00` |
| Space | 41 | `00 00 FF` |
| Right Arrow | 89 | `FF FF FF` |

The installed driver's `Ry5088_x68v2_8k_DM` matrix for internal ID `2902` supplies the full
66-key physical map. Its Escape, A, Space, and Right Arrow slots agree exactly with the four
sparse capture anchors above. On 2026-09-20, this implementation uploaded a five-row test:
red, green, blue, magenta, and white. The user visually confirmed all five rows on the
physical keyboard, establishing arbitrary static addressing for all 66 exposed keys as
**HARDWARE VERIFIED**.

The firmware matrix has 126 RGB slots; only the 66 mapped physical slots are populated and
all unused slots are zero. Because this verified path is flash-backed, continuous per-key
animation is unsupported on the tested revision unless a separate volatile opcode is
discovered.

## Music-follow mode

A controlled mode-22 capture on 2026-09-08 selected the mode with:

```text
07 16 04 04 00 FA FF FA E7
```

The local helper then emitted 3,909 host-to-device reports over about 80 seconds at
approximately 49 FPS.
Every report had this eight-byte header and a valid `Bit7` checksum:

```text
0D 00 00 00 00 00 00 F2
```

Re-analysis of the complete 64-byte reports on 2026-09-20 corrected the earlier prefix-only
interpretation. Bytes 1-6 stayed zero and bytes 8-39 carry a 32-byte volatile body. The
controlled frequency-sequence capture (`mode22-frequency-sequence-20260920.pcap`, SHA-256
`6C0253445FE8E8310E0EDFEAD169E05C24CE0A9B743BD341E408EAC442E89AA8`) contained 8,979
`0x0D` reports. Across the capture, body values ranged from `0` to `6`; the selected
frequency segments produced these peak-bin observations:

| System-output tone | Peak bin | Capture-relative active interval |
| ---: | ---: | ---: |
| 110 Hz | 2 | 147.420–150.723 s |
| 220 Hz | 5 | 152.430–155.729 s |
| 440 Hz | 9 | 157.419–160.737 s |
| 880 Hz | 19 | 162.421–165.726 s |

The 1760 Hz and 3520 Hz segments produced no active report body, consistent with the
observed 32-bin low-frequency range. The earlier 2026-09-08 five-second 440 Hz capture
(the separate 3,909-report capture listed below) contained 260 consecutive reports with a
non-zero body for 5.30 seconds; 244 used this dominant 32-byte body:

```text
00 00 00 00 00 00 00 00 02 06 06 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
```

The other 16 reports form short ramp-up and ramp-down transitions. This proves that the
helper samples system output and sends a volatile 32-bin representation after the checksum.
The spatial meaning of the bins and their relationship to physical keys remain **CAPTURE
NEEDED**. The shape is consistent with spectrum levels or column heights, but it is not
evidence of arbitrary per-key RGB addressing. No public per-key frame API is provided until
controlled replay and observed keyboard output identify the rendering path.

The repository includes a guarded replay probe for that observation step. It selects mode
22, sends only the four dominant 32-bin bodies sanitized from the controlled capture, caps
levels at the observed range `0..6`, and restores the exact state read before acquisition:

```powershell
.\.venv\Scripts\python.exe tools\replay_spectrum_probe.py
```

Opcode `0x0D` remains absent from the REST and WebSocket APIs. The HID transport applies a
second shape check to its header, 32-bin body, and zero trailer before transmitting it.

During the first physical replay on 2026-09-20, the captured low-frequency profiles were
observed as diagonal illuminated bands running from left to right. Each band was about two
to three keys wide and tilted slightly left. Repeated replay of the 880 Hz profile produced
no visible lighting.
This is user-observed evidence that firmware maps spectrum bins into spatial bands; it does
not yet establish the exact bin-to-key transform. A later isolated-bin replay at bins 0, 8,
16, 24, and 31 did not produce a clearly progressing single diagonal band, suggesting that
the renderer requires an adjacent-bin cluster. The same probe can replay a captured-width
`1,6,6,1` cluster at selected starting positions for the next mapping step:

```powershell
.\.venv\Scripts\python.exe tools\replay_spectrum_probe.py `
  --bands 0,5,10,15,20,25,28 `
  --interactive
```

Interactive mode continuously refreshes one pattern while its exact bin range is visible in
the local console. Enter inserts a half-second zero frame and advances; `Q` exits and restores
the prior lighting. This avoids relying on timed transitions or unseen labels.

The physical patterns remained irregular, with unlit keys inside the apparent diagonal
groups, and were not practical to describe as a stable key map. Combined with the frequency
correlation, this establishes `0x0D` as input to a firmware-defined spectrum effect rather
than a direct or per-key LED protocol. It remains useful for controlled research and custom
audio visualization, but it does not satisfy the volatile per-key capability checkpoint for
OpenRGB integration.

## Vendor-driver correlation

Static inspection of the installed 3.1.12 driver explains where the host-driven modes are
started, without treating minified code as a protocol specification. The renderer bundle
`resources/app/dist/js/index.b078bf5f.js` constructs a gRPC client at
`http://127.0.0.1:3814`, exposes `sendRawFeature`, and maps `LightMusicFollow2` to the
helper's `Music2` light type. The X68HE bundle `resources/app/dist/js/e56738b7.js` confirms
mode index `22` and the gen2 speed encoding. The native `resources/app/iot_driver.exe`
contains WASAPI, microphone, spectrum, `watchSystemInfo`, and `sendRawFeature` strings.

This places audio processing in the native helper rather than the renderer. The corrected
capture establishes system-output loopback as an active source for mode 22.

### Native-helper command inventory

Static inspection of the installed `iot_driver.exe` on 2026-09-20 found the compiled command
names and values used by its gen2 HID path:

```text
FEA_CMD_SET_LEDPARAM = 0x07
FEA_CMD_SET_USERPIC  = 0x0C
FEA_CMD_SET_AUDIO    = 0x0D
FEA_CMD_SET_WINDOS   = 0x0E
```

The renderer calls the helper's `setLightType` RPC with only `Music2`, `Screen`, or `Other`.
For the X68HE, the JavaScript device class uses `0x07` to select modes, `0x0C` to upload
custom per-key pages, and delegates modes 21 and 22 to that helper. Together with the USB
captures, this is strong evidence that Driver v4 3.1.12 exposes no additional volatile
per-key lighting command: screen colour uses `0x0E`, music uses `0x0D`, and custom per-key
data uses flash-backed `0x0C`. This does not prove that an undocumented keyboard-firmware
command is impossible, but it closes the remaining driver-exposed search path.

### Rejected USERGIF candidate and firmware lookup

The gen2 base class in the installed renderer also implements `SET_USERGIF 0x12` for
devices that advertise `LightUserColor`. This is an onboard animation upload rather than a
live frame command. The renderer starts an upload, waits 300 ms, and then writes every
animation frame as seven paged reports containing a frame number, frame delay, and 126 RGB
slots. Some other ROYUAN families use a different `SET_USERGIF` opcode, so the numeric value
must not be generalized across controllers.

The X68HE records for internal IDs `2270`, `2472`, and `2902` all use a light layout that
omits `LightUserColor`. Their exposed host-driven modes stop at music follow and screen
colour. Consequently, `0x12` is not allowlisted or probed on this keyboard: the installed
driver supplies no evidence that X68HE firmware accepts it, and its upload structure is
storage-oriented even on models that do.

The driver's official firmware lookup was reproduced on 2026-09-20. It sends an Axios JSON
`POST` to:

```text
https://api2.rongyuan.tech:3816/api/v2/get_fw_version
{"dev_id": 2902}
```

The service returned HTTP 500 with `Record not found`. The same response was returned for
the other documented X68HE IDs, `2270` and `2472`. No `file_path` was supplied, so there is
no official firmware image available through the installed driver's metadata path for
offline dispatcher analysis. A historical public X68HE release contains a 101,868,672-byte
Windows driver installer with SHA-256
`3EE70880C8B5ADCD469A0E3EBEFA7E280A22FA23FF74E369955511A2C58E04A2`; it is not a confirmed
standalone keyboard firmware image and was not executed or used as protocol evidence.

At this checkpoint, arbitrary per-key control is fully verified only for occasional static
patterns through guarded `0x0C` uploads. A safe direct-mode implementation would require an
exact X68HE firmware image or a capture from a vendor implementation that emits volatile
per-key frames. Blind opcode probing cannot establish that safely and remains disabled.

## Blocked command classes

The transport rejects every write except allowlisted lighting commands. USERPIC is accepted
only when it matches the captured slot-0, seven-page format, page lengths, final-page flag,
checksum, and zero padding. In particular the package never exposes reset, bootloader,
firmware update, calibration, flash erase, keymap, macro, screen-storage, or magnetic-switch
opcodes.

Sources:

- https://getsharkfin.com/boards/attack-shark-x68he
- https://github.com/dniminenn/sharkfin/blob/master/docs/PROTOCOL.md
