# USB protocol (reverse-engineered) and feature status

## Feature status

| Feature | Status | Detail |
|---|---|---|
| **Scout Mode** | ✅ Working | Frame validated on hardware, USB traffic identical to the Creative application |
| **Direct Mode** | ✅ Working | `0x39` frame validated, state read + reconnection after the card's USB reset |
| **Sound Mode** | ✅ Working | 51 modes (games, music, generic equalizers) reverse-engineered from dedicated captures, `0x12` frame per parameter |
| **10-band equalizer + Preamp** | ✅ Working | Manual editing via slider, `0x12` frame per band, validated on hardware |
| **Bass / Treble** | ⚠️ Approximate | No dedicated parameter on the card: rewrites the 10 bands based on a curve estimated from a Wireshark capture, not guaranteed identical to Creative |
| **CrystalVoice** (Noise Reduction, Acoustic Echo Cancellation, Smart Volume) | ✅ Working | `0x12` frame per parameter, same mechanism as the equalizer but with a dedicated TLV marker (`0x95`), reverse-engineered from Wireshark captures |
| **Voice Morph** | ✅ Working | 18 presets replayed as a sequence of 8 `0x12` writes (marker `0x95`), plus a dedicated on/off parameter |
| **Microphone Equalizer** | ✅ Working | 9 presets replayed as a sequence of 10 `0x12` writes (marker `0x95`), plus a dedicated on/off parameter |
| **Decoder** (Dolby Digital, Dynamic Range Control) | ✅ Working | 3 modes (Normal / Full / Night), one `0x12` write with a third TLV marker (`0x97`), reverse-engineered from a Wireshark capture |

Unimplemented features are greyed out in the interface: they don't
pretend to act on the card until the corresponding frame has been
identified (see [contributing.md](contributing.md)).

## HID interfaces

The card (VID `041e` / PID `329b`) exposes two HID interfaces:

| Interface | Usage page | Role |
|---|---|---|
| 3 | `0x000C` (Consumer) | media keys, 16 B input reports |
| **4** | **`0xFF01` (Vendor)** | **control channel**, EP `0x85` interrupt IN, 64 B reports |

⚠️ Opening the card with `hid.device().open(VID, PID)` can land on
interface 3, which **rejects** commands. The driver explicitly selects
the control interface: `usage_page == 0xFF01`, falling back to
`interface_number == 4` (the libusb backend's case, which doesn't
enumerate `usage_page`), and as a last resort `input_report_length == 64`.

## HID transport

Interface 4 **has no interrupt OUT endpoint**. Every write is therefore a
`SET_REPORT` control transfer, and the capture shows **only one**
transport, for both Scout Mode and Direct Mode:

```
bmRequestType = 0x21   (Host→Device, Class, Interface)
bRequest      = 0x09   (SET_REPORT)
wValue        = 0x0200 (report type 0x02 = Output, report ID 0x00)
wIndex        = 4      (interface number)
wLength       = 64     (full report, zero-padded frame)
```

On the Python side, `hid_write()` consumes the **first byte as the report
ID**: so the driver always writes `b"\x00" + pad_report(frame)`, i.e. 65
bytes, to get `wValue = 0x0200` and `wLength = 64`.

```
Scout ON   : 5a 26 05 07 02 00 01 00  + 56 zeros
Direct ON  : 5a 39 03 00 05 01        + 58 zeros
```

The three possible hidapi paths:

| Backend | What `hid_write(b"\x00" + 64 B)` does | `usage_page` listed |
|---|---|---|
| macOS / IOKit | `IOHIDDeviceSetReport(Output, id=0, 64 B)` | ✅ |
| Linux / hidraw | `write(/dev/hidrawN)` then automatic fallback to `HID_REQ_SET_REPORT` for lack of an OUT EP | ✅ |
| Linux / libusb | detaches `usbhid`, no OUT EP → direct `SET_REPORT` control transfer | ❌ (always 0) |

One safety net remains: if no response arrives with the padded form, the
driver retries **exactly once** with the old form (bare frame, report ID
`0x5A`, `wValue = 0x025A`) and explicitly logs it.

### Framing

```
+------+--------+--------+------------------+
| 0x5A | type   | length | payload          |
+------+--------+--------+------------------+
```

`length` = payload size (3-byte header excluded).
The `0x80` bit in `type` signals a rejection by the card.

### SET u16 command (type `0x26`)

```
payload = <feature:1> <param:u16 LE> <value:u16 LE>

Scout Mode ON  : 5a 26 05 07 02 00 01 00
Scout Mode OFF : 5a 26 05 07 02 00 00 00
```

### Direct Mode (type `0x39`)

```
write ON       : 5a 39 03 00 05 01      -> ACK 5a 02 0a 39 00 05 01
write OFF      : 5a 39 03 00 05 00      -> ACK 5a 02 0a 39 00 05 00
status read    : 5a 39 05 01 20 00 00 00
response       : 5a 39 05 01 <bits> 40 00 00   (bit 0x20 -> Direct Mode active)
```

⚠️ The `0x39` ACK **doesn't have the same layout** as the `0x26` one:
`<cmd> <status> <param> <value>` instead of
`<cmd> <status> <feature> <param:u16> <value:u16>`. Hence the dedicated
accessors `Frame.dm_ack_param` / `Frame.dm_ack_value`.

### USB reset after a Direct Mode toggle

Direct Mode reconfigures the audio chain: **the card re-enumerates**.
Timeline measured on a Wireshark capture, starting from the `0x39` command:

| Time | Event |
|---|---|
| +0.0002 s | ACK `5a 02 0a 39 00 05 xx` |
| +0.005 s | `0x1a` notifications then `0x11` dumps |
| **+0.6 s** | **USB reset / disconnect** → the old HID handle is dead |
| +1.3 s | the device reappears (new `/dev/hidrawN`, new `path`) |

`set_direct_mode()` therefore chains: purge → send 64 B → wait for the ACK
(300 ms budget) → drain the `0x1a`/`0x11` frames → `reconnect()`. The
reconnection closes the old handle, waits 1 s of grace, then re-enumerates
every 250 ms for up to 12 s and **validates every open with a real
round-trip** (`5a 09 01 02` → `0x09` response containing the firmware
version, `1.2.250819.0903` on the reference card): a handle opened on the
dying node accepts the `open` but no longer responds.

Consequence for the interface: a Direct Mode toggle takes 2 to 4 seconds.
The GUI runs it in a worker thread, disables the switch, and shows
"reconnecting the device…".

### Card → host (EP `0x85`, 64 bytes)

```
ACK (type 0x02)   : 5a 02 0a 26 00 07 02 00 01 00 ...
                    └ cmd 0x26, status 0x00 (OK), feature/param/value echo

Notification 0x1a : "a setting changed", emitted in a burst after a 0x39

Info response 0x09: contains the firmware version in ASCII

Parameter dump (type 0x11):
  5a 11 <len> <count:u16> then N 6-byte entries: 96 <id> <float32 LE>
  e.g. 96 05 a4 70 3d 3f  ->  param 0x05 = 0.74
       96 00 00 00 80 3f  ->  param 0x00 = 1.0
```

### Sound Mode (type `0x12`, confirmed)

Each sound mode of the Creative application (one dedicated Wireshark
capture per mode) sends an ordered sequence of **`CMD_SET_FLOAT`** writes:

```
payload (7 bytes) = 0x01 0x96 <param_id:1> <value:f32 LE>

writing band 0x0b = -4.0 dB : 5a 12 07 01 96 0b 00 00 80 c0
ACK                          : 5a 02 0a 12 00 ...
```

`0x96` is the same TLV marker as the one used in `0x11` dump entries
(`0x01` is a constant prefix, role not identified). Confirmed parameters:

- param `0x00`: SBX master (0/1)
- param `0x01`: master gain/compensation
- param `0x09`: equalizer on/off
- params `0x0b`–`0x14`: the 10 equalizer bands, in dB
- param `0x0a`: **Preamp** (input gain, in dB)

⚠️ `0x0a` was `0.0` in all 51 sound-mode captures, which initially
suggested a preset id ("0 = manual"). A Wireshark capture of individual
slider variations (sliding from `+6.1` to `-8.5`) shows it's actually a
full-fledged slider, just like a band - simply left at 0 dB by all
captured modes.

Other parameters appear depending on the mode (`0x02`, `0x04`/`0x05`,
`0x07`/`0x08`, `0x18`/`0x19`...), probably sub-settings of the
"acoustic engine" (Crystalizer, Surround...): their exact role isn't
identified, but replaying the full captured sequence is enough to apply
the mode correctly. No USB reset is triggered by these writes.

The per-mode sequences are generated from the captures by
`tools/extract_sound_modes.py` into `soundblaster_g8/sound_modes.py` (see
[contributing.md](contributing.md) to add a mode).

### Bass / Treble (approximate, no dedicated parameter)

That same capture shows that the Bass and Treble sliders have
**no** parameter of their own: moving them rewrites the existing 10 bands
(`0x0b`-`0x14`) with a "tilt" curve (decreasing emphasis from one end of
the spectrum, the other end left unchanged). `controller
.nudge_eq_tilt` applies a linear approximation of this curve,
calibrated on the deltas measured in this capture
(`BASS_TILT_WEIGHTS`/`TREBLE_TILT_WEIGHTS` in `controller.py`): this is
**not guaranteed identical** to Creative's actual algorithm, for lack of
a complete parametric capture (several isolated slider positions).

### Equalizer activation

It contains no write to `param 0x09`: the Creative
app enables the equalizer elsewhere (probably when opening the EQ tab),
not on every slider gesture. Without this, band writes are indeed
acknowledged by the card but remain inaudible while the EQ master is off
(active mode "Disabled"). So the app automatically enables `param 0x09`
(`controller.ensure_eq_enabled`) when entering the Equalizer page.

### CrystalVoice (Noise Reduction, Echo Cancellation, Smart Volume, Voice Morph, Mic Equalizer)

Same mechanism as Sound Mode/EQ (`CMD_SET_FLOAT`, type `0x12`), but with a
**dedicated TLV marker `0x95`** instead of `0x96`: CrystalVoice and
EQ/sound-mode parameters reuse the same numeric ids (e.g. `0x00`, `0x04`,
`0x05`), so the marker is what disambiguates the two namespaces - both on
write (`payload = 0x01 0x95 <param> <f32 LE>`) and on the `0x11` parameter
dump the card sends back after a write.

```
writing Noise Reduction ON: 5a 12 07 01 95 04 00 00 80 3f
ACK                        : 5a 02 0a 12 00 ...
dump (0x11)                : ... 95 04 00 00 80 3f ...  (kind=0x95, param=0x04, value=1.0)
```

Parameters confirmed from Wireshark captures:

- param `0x00`: Acoustic Echo Cancellation (0/1)
- param `0x04`: Noise Reduction on/off (0/1)
- param `0x05`: Noise Reduction level, float **0.0-1.0** (continuous, 30 samples captured while dragging the slider)
- param `0x0a`: Voice Morph on/off (0/1)
- params `0x0b`-`0x12`: the 8 Voice Morph parameters (one preset)
- param `0x13`: Microphone Equalizer on/off (0/1)
- params `0x14`-`0x1d`: the 10 Microphone Equalizer bands, in dB
- param `0x2c`: Smart Voice on/off (0/1)

Because the marker matters, `protocol.DecodedState.params` is keyed by
`(marker, param_id)`, not by `param_id` alone (a flat dict on `param_id`
would silently mix an EQ/sound-mode value with a CrystalVoice one sharing
the same id).

#### Voice Morph and Microphone Equalizer presets

Both work like a sound mode: a preset is an ordered sequence of `0x12`
writes replayed as-is from the capture (`driver.set_crystalvoice_params`).
The two families were extracted into `soundblaster_g8/crystalvoice_presets.py`
by `tools/extract_crystalvoice_presets.py`, from one capture per preset:

```bash
python tools/extract_crystalvoice_presets.py --input ~/Documents/pcap
```

- `CrystalVoice-VoiceMorph-<name>.pcapng` → 18 presets, params `0x0b`-`0x12`
- `CrystalVoice-MicroEqualizer-<name>.pcapng` → 9 presets, params `0x14`-`0x1d`

The enable bit (`0x0a` / `0x13`) is **never** part of a preset: the Creative
application writes it only when the user flips the feature's switch. A preset
applied while the feature is off is acknowledged by the card but inaudible -
the same trap as `param 0x09` for the equalizer. Hence the GUI pairing a
toggle with each dropdown, the dropdown being greyed out while the toggle is
off.

Two mic-EQ captures, `broadcast` and `pitch-reduction`, yield byte-identical
band values `(0, 0, 2, 2, -2, 0, -4, 4, 0, 0)`. This was reproduced across two
separate capture sessions, so it is kept as-is rather than treated as a
capture error.

### Decoder (Dolby Digital Dynamic Range Control)

A third float namespace on the same `CMD_SET_FLOAT` frame, with marker
**`0x97`**. One click on a mode = one write, acknowledged then echoed in the
`0x11` dump:

```
Normal : 5a 12 07 01 97 02 00 00 00 40   (param 0x02 = 2.0)
Full   : 5a 12 07 01 97 02 00 00 80 3f   (param 0x02 = 1.0)
Night  : 5a 12 07 01 97 02 00 00 40 40   (param 0x02 = 3.0)
ACK    : 5a 02 0a 12 00 ...
dump   : 5a 11 08 01 00 97 02 <f32>      (kind=0x97, param=0x02)
```

The values are **not** contiguous with the display order (Normal, Full,
Night). As for Scout Mode and Sound Mode, no read
frame for the active mode has been observed, so the GUI tracks the last
acknowledged command (`controller.DECODER_MODES`).
