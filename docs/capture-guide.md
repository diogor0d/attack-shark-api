# Controlled USB capture guide

Raw USB captures may contain sensitive input traffic. Store them outside the repository and
never commit them. The current machine uses
`%LOCALAPPDATA%\AttackSharkX68HE\captures`.

## Prerequisites

- Attack Shark X68HE connected by USB.
- Attack Shark Driver v4 3.1.12.
- Wireshark 4.4.5 and USBPcap 1.5.4.0. USBPcap was installed and its kernel service was
  verified running after a Windows restart on 2026-09-08.
- No Sharkfin, OpenRGB, or custom API process using the keyboard.

On the tested machine the standalone USBPcap executable is not in Wireshark's default
extcap directory. Point Wireshark tools at it for the current PowerShell session:

```powershell
$env:WIRESHARK_EXTCAP_DIR = 'C:\Program Files\USBPcap'
& 'C:\Program Files\Wireshark\tshark.exe' -D
```

The connected keyboard currently resolves to `\\.\USBPcap2`, USB device address `4`.
Recheck the address after unplugging, reconnecting, resuming, or restarting Windows; USB
addresses are not persistent. The extcap configuration lists current addresses:

```powershell
& 'C:\Program Files\USBPcap\USBPcapCMD.exe' --extcap-config --extcap-interface '\\.\USBPcap2'
```

## Capture matrix

Record a separate short capture for each action:

1. Open the vendor driver and wait for device detection.
2. Start capture on the USBPcap interface containing `3151:502D`, selecting only its current
   USB device address.
3. Perform exactly one labelled lighting action.
4. Wait two seconds and stop capture.
5. Record the USB device address and action in a sidecar note.

Actions: static red, green, blue, white, off, a sparse per-key pattern, mode 21 with controlled
red/green/blue screen patches, and mode 22 with silence plus a fixed test tone.

Do not type passwords or other sensitive text while capturing. Close unrelated USB software
where practical.

The included capture launcher creates a new file under the local capture directory and
refuses to overwrite an existing capture. Run it from an Administrator PowerShell after
checking the current filter device and USB address:

```powershell
.\tools\start_usb_capture.ps1 `
  -CaptureName mode22-music-20260908 `
  -DeviceAddress 4 `
  -FilterDevice '\\.\USBPcap2'
```

Stop it with `Ctrl+C` after the controlled action finishes.

## Captures used by the current notes

These raw files remain outside Git under `%LOCALAPPDATA%\AttackSharkX68HE\captures`:

| File | SHA-256 | Result |
| --- | --- | --- |
| `preset-sequence-20260908.pcap` | `169c4dfe7f90c22d90e01bda5274215e2dcbbdbe3c69edec8f35ea99b9455e9b` | `0x07` preset writes |
| `mode21-sequence-20260908.pcap` | `da23635931f7e43f7a430e248cbf38b02b658a30074e8ea567164b4cbd97ef2d` | `0x0E` whole-keyboard RGB |
| `custom-pattern-20260908.pcap` | `0d3fd4a0cb006cf34d9b940c2d21a6317248cc6264f89e856acd86b5ed9e7959` | `0x0C` flash-backed pages |
| `mode22-music-20260908.pcap` | `b3f1d875d14d7af991954070cdc6eadaf4dce278334813c368ea4a52b1988135` | `0x0D` cadence, zero payload |

The mode-21 hash is recorded from the capture used for the protocol notes; recompute it
locally if the file is replaced.

## Sanitization and analysis

Run:

```powershell
.\.venv\Scripts\python.exe tools\analyze_capture.py `
  "$env:LOCALAPPDATA\AttackSharkX68HE\captures\mode21-red.pcap" `
  --device-address 4
```

For high-rate host-driven captures, request an aggregate view so raw report records are not
printed to the terminal:

```powershell
.\.venv\Scripts\python.exe tools\analyze_capture.py `
  "$env:LOCALAPPDATA\AttackSharkX68HE\captures\mode22-microphone-20260920.pcap" `
  --device-address 1 `
  --summary-only
```

The remaining controlled experiment is mode 22 with a sequence of fixed system-output
frequencies separated by silence. The existing 440 Hz capture proves that bytes 8-21 carry
a volatile 14-value body while bytes 1-6 remain zero. New captures should establish which
body positions respond to frequency and amplitude, then correlate those values with the
physical keyboard. Even if these are spectrum bands or column heights, that would not prove
arbitrary per-key RGB addressing. Recheck the USB address immediately before capture; the
`1` above is only an example and is not persistent.

After capture is running and Music Sync is selected in Attack Shark Driver, play the
deterministic 33-second sequence:

```powershell
.\.venv\Scripts\python.exe tools\play_frequency_sequence.py
```

The command prints the exact tone timeline before playback so frequency transitions can be
correlated with report timestamps.

The analyzer asks TShark for control-transfer payloads belonging to only the selected USB
device address, summarizes opcodes, checks known checksum positions, and flags prohibited
opcodes. Review its JSON output before creating a sanitized fixture containing only the
64-byte vendor reports needed for tests.

Before enabling streaming, prove all of the following:

- A frame changes arbitrary individual keys without using opcode `0x0C`.
- No frame command erases or commits flash.
- The packet sequence restores cleanly after disconnect.
- A 15-minute test at 10 FPS does not stall the control endpoint or affect typing.
