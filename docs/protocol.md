# X68HE protocol notes

Status date: 2026-09-08

Evidence labels used below:

- **LOCAL**: observed in the installed Attack Shark Driver v4 3.1.12 or Windows device data.
- **CAPTURED**: observed in a controlled USBPcap capture from the connected keyboard.
- **UPSTREAM**: documented by the independent Sharkfin protocol research.
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

The package also has a capture-derived encoder for volatile whole-keyboard opcode `0x0E`,
but it is not exposed through the public API. Sending arbitrary raw reports is not part of
the package interface.

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

`SET_USERPIC 0x0C` is not a live-frame mechanism. Published research says it commits RGB
patterns to flash and that repeated uploads can stall some related controllers. It is
therefore blocked for both the API and experimental animation.

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

The remaining physical-to-matrix mapping is intentionally unverified. Because the only
observed per-key path is flash-backed, continuous per-key animation is unsupported on the
tested revision unless a separate volatile opcode is discovered.

## Music-follow mode

A controlled mode-22 capture on 2026-09-08 selected the mode with:

```text
07 16 04 04 00 FA FF FA E7
```

The local helper then emitted 3,909 host-to-device reports over about 80 seconds at
approximately 49 FPS.
Every report had this eight-byte prefix and a valid `Bit7` checksum:

```text
0D 00 00 00 00 00 00 F2
```

The payload stayed zero during silence and during a confirmed five-second, 440 Hz system
output tone. This establishes opcode `0x0D` and its update cadence, but it does not establish
the meaning of bytes 1-6 or which audio source the helper samples. No encoder or public API
is provided until a non-zero controlled capture identifies those fields.

## Vendor-driver correlation

Static inspection of the installed 3.1.12 driver explains where the host-driven modes are
started, without treating minified code as a protocol specification. The renderer bundle
`resources/app/dist/js/index.b078bf5f.js` constructs a gRPC client at
`http://127.0.0.1:3814`, exposes `sendRawFeature`, and maps `LightMusicFollow2` to the
helper's `Music2` light type. The X68HE bundle `resources/app/dist/js/e56738b7.js` confirms
mode index `22` and the gen2 speed encoding. The native `resources/app/iot_driver.exe`
contains WASAPI, microphone, spectrum, `watchSystemInfo`, and `sendRawFeature` strings.

This places audio processing in the native helper rather than the renderer. The captured
zero payload does not distinguish a render-loopback endpoint from a microphone endpoint, so
the source remains **CAPTURE NEEDED**. No client-side attempt is made to reproduce it.

## Blocked command classes

The transport rejects every write except allowlisted lighting commands. In particular it
must never expose reset, bootloader, firmware update, calibration, flash erase, keymap,
macro, USERPIC, screen-storage, or magnetic-switch opcodes.

Sources:

- https://getsharkfin.com/boards/attack-shark-x68he
- https://github.com/dniminenn/sharkfin/blob/master/docs/PROTOCOL.md
