# Sound Blaster G8 Control

Open-source control application for the **Creative Sound Blaster G8** sound card,
on **macOS** and **Linux** (Windows possible via hidapi, untested).

## Feature status

| Feature | Status | Detail |
|---|---|---|
| **Scout Mode** | ✅ Working | Frame validated on hardware, USB traffic identical to the Creative application |
| **Direct Mode** | ✅ Working | `0x39` frame validated, state read + reconnection after the card's USB reset |
| **Sound Mode** | ✅ Working | 51 modes (games, music, generic equalizers) reverse-engineered from dedicated captures, `0x12` frame per parameter |
| **10-band equalizer + Preamp** | ✅ Working | Manual editing via slider, `0x12` frame per band, validated on hardware |
| **Bass / Treble** | ⚠️ Approximate | No dedicated parameter on the card: rewrites the 10 bands based on a curve estimated from `Equalizer-manual.pcapng`, not guaranteed identical to Creative |
| CrystalVoice | ⛔ Not implemented | USB frame not yet captured |

Unimplemented features are greyed out in the interface: they don't
pretend to act on the card until the corresponding frame has been
identified (see *Contributing to the reverse engineering* below).

The interface is bilingual (English/French), with a language selector in
the header; the choice persists across restarts.

## Installation

```bash
pip install -e .
```

### Linux

#### hidapi backend: hidraw or libusb

`pip install hidapi` installs **two** Python modules on Linux:

| Module | Backend | `usage_page` listed | Kernel driver |
|---|---|---|---|
| `hid` | **libusb** (the one from the binary wheels, so the default) | ❌ always `0` | detaches `usbhid` during access |
| `hidraw` | **hidraw** | ✅ read from sysfs | kept |

`soundblaster_g8/hidbackend.py` **prefers `hidraw`** and falls back to `hid`
(libusb). The selected backend is logged on startup and shown by:

```bash
python tools/g8_probe.py --backend
```

To get the `hidraw` module, hidapi must be compiled locally:

```bash
sudo apt install libudev-dev libusb-1.0-0-dev   # or your distro's equivalent
HIDAPI_WITH_HIDRAW=1 pip install --no-binary :all: hidapi
```

Consequences of the libusb backend:

- `hid_enumerate()` doesn't populate `usage_page`: the control interface is
  selected on `interface_number == 4` (the **normal** path in this case, not
  a degraded mode).
- libusb **detaches the kernel driver** `usbhid` from the interface for the
  duration of the access: the card's media keys may stop responding during
  that time, and access requires the parent USB device (see the udev rule).

#### Access rights (udev)

```bash
sudo cp udev/99-soundblaster-g8.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

The `KERNEL=="hidraw*"` rule covers the hidraw backend, the
`SUBSYSTEM=="usb"` rule is **mandatory for libusb** (usbfs access + kernel
driver detachment). `TAG+="uaccess"` is enough for a local session;
`GROUP="plugdev"` is simply ignored on distributions without that group
(Fedora, Arch...).

⚠️ **Race with udev**: after the USB reset triggered by a Direct Mode
toggle, the new `/dev/hidrawN` can appear before udev has applied
permissions. The driver therefore retries the open (`PermissionError`
treated as transient) for 12 seconds.

⚠️ **`uaccess` isn't always reliable on hotplug**: on some sessions
(observed under COSMIC/Wayland), the `uaccess` ACL is only applied by
`systemd-logind` for devices already present when the session opens - not
for ones that appear afterward (USB reset, replug). In that case, the 12
seconds of retries above are never enough: *every* state read times out
(including on the app's very first startup), and reconnection after a
Direct Mode toggle systematically fails. If you observe this symptom,
explicitly add yourself to the `plugdev` group (independent of `uaccess`,
applied synchronously by the udev rule):

```bash
sudo usermod -aG plugdev "$USER"
# then log out/back in (or: newgrp plugdev / sg plugdev -c ...)
```

#### Microphone disabled at startup (ALSA capture source)

The `snd-usb-audio` kernel driver initializes the ALSA "PCM Capture
Source" control to `Line In` instead of `External Mic`: the microphone
therefore picks up nothing until the source is changed manually, on every
restart of the card.

The application re-applies this fix on every startup
(`soundblaster_g8/alsa_fix.py`). For the microphone to work even without
launching the app (e.g. right after plugging in the card), also install the
system-level fix:

```bash
sudo alsa-fix/install.sh
```

See `alsa-fix/README.md` for details (udev rule + script, uninstallation).

### macOS

No special configuration needed: HID access to vendor interfaces is
allowed without elevated privileges (IOKit backend).

## Usage

```bash
python main.py          # graphical interface
soundblaster-g8         # after installation
```

### Command-line tool

`tools/g8_probe.py` lets you drive and diagnose the card without a GUI:

```bash
python tools/g8_probe.py --backend           # selected hidapi backend (hidraw/libusb/iokit)
python tools/g8_probe.py --list              # detected HID interfaces
python tools/g8_probe.py --selftest          # validates encoding without hardware
python tools/g8_probe.py --scout on --debug  # enables Scout Mode
python tools/g8_probe.py --scout off
python tools/g8_probe.py --direct on --debug # enables Direct Mode (USB reset)
python tools/g8_probe.py --direct-status     # reads Direct Mode's state
python tools/g8_probe.py --reconnect-test 5  # 5 consecutive Direct Mode toggles
python tools/g8_probe.py --monitor           # listens to the card's notifications
python tools/g8_probe.py --raw 26 0702000100 # sends an arbitrary frame
python tools/g8_probe.py --set 07:0002=1     # writes a parameter (feature:param=value)
python tools/g8_probe.py --list-sound-modes  # lists the available sound modes
python tools/g8_probe.py --sound-mode esport --debug  # applies a sound mode
```

## Building a .deb package

A native Debian source package (`debian/`) is provided, built with
`dh-python`/`pybuild` against the system Python (no PyInstaller
involved: the package depends on `python3-hid`, which ships the `hid`
and `hidraw` modules on Debian/Ubuntu, and `python3-tk`):

```bash
sudo apt install debhelper dh-python pybuild-plugin-pyproject \
    python3-all python3-setuptools gettext
dpkg-buildpackage -us -uc -b
```

This produces `../soundblaster-g8_0.1.0-1_all.deb`. Install it with:

```bash
sudo apt install ../soundblaster-g8_0.1.0-1_all.deb
```

The package installs the application (`soundblaster-g8` on `$PATH`), a
menu entry with icon, and the HID udev rule
(`udev/99-soundblaster-g8.rules`, see *Access rights (udev)* above) -
so, unlike the manual install, no `sudo cp` / `udevadm trigger` step is
needed for the card to be accessible without root. The optional ALSA
fix (`alsa-fix/install.sh`) is not part of the package and still needs
to be installed separately if desired (the app re-applies the same fix
at every startup regardless, see *Microphone disabled at startup*
above).

## USB protocol (reverse-engineered)

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
Timeline measured on the pcap, starting from the `0x39` command:

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

Each sound mode of the Creative application (one
`Equalizer-*.pcapng` file per mode in the dedicated captures) sends an
ordered sequence of **`CMD_SET_FLOAT`** writes:

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
suggested a preset id ("0 = manual"). The
`Equalizer-manual.pcapng` capture (individual slider variations, sliding
from `+6.1` to `-8.5`) shows it's actually a full-fledged slider, just
like a band - simply left at 0 dB by all captured modes.

Other parameters appear depending on the mode (`0x02`, `0x04`/`0x05`,
`0x07`/`0x08`, `0x18`/`0x19`...), probably sub-settings of the
"acoustic engine" (Crystalizer, Surround...): their exact role isn't
identified, but replaying the full captured sequence is enough to apply
the mode correctly. No USB reset is triggered by these writes.

The per-mode sequences are generated from the captures by
`tools/extract_sound_modes.py` into `soundblaster_g8/sound_modes.py` (see
"Contributing to the reverse engineering" below to add a mode).

### Bass / Treble (approximate, no dedicated parameter)

`Equalizer-manual.pcapng` shows that the Bass and Treble sliders have
**no** parameter of their own: moving them rewrites the existing 10 bands
(`0x0b`-`0x14`) with a "tilt" curve (decreasing emphasis from one end of
the spectrum, the other end left unchanged). `controller
.nudge_eq_tilt` applies a linear approximation of this curve,
calibrated on the deltas measured in this capture
(`BASS_TILT_WEIGHTS`/`TREBLE_TILT_WEIGHTS` in `controller.py`): this is
**not guaranteed identical** to Creative's actual algorithm, for lack of
a complete parametric capture (several isolated slider positions).

### Equalizer activation

`Equalizer-manual.pcapng` contains no write to `param 0x09`: the Creative
app enables the equalizer elsewhere (probably when opening the EQ tab),
not on every slider gesture. Without this, band writes are indeed
acknowledged by the card but remain inaudible while the EQ master is off
(active mode "Disabled"). So the app automatically enables `param 0x09`
(`controller.ensure_eq_enabled`) when entering the Equalizer page.

## Contributing to the reverse engineering

To add a feature (Direct Mode, CrystalVoice, EQ...):

1. Capture traffic while the official Creative application changes
   **a single** setting:

   ```bash
   # macOS (XHC2 interface depending on the port used)
   tshark -i XHC2 -w setting.pcapng -a duration:15
   # Linux
   sudo modprobe usbmon && tshark -i usbmon1 -w setting.pcapng -a duration:15
   ```

2. Extract the emitted commands:

   ```bash
   tshark -r setting.pcapng -V | grep -E "CONTROL response data|Leftover Capture Data"
   ```

3. Identify the `feature` / `param` pair in the payload, then test it:

   ```bash
   python tools/g8_probe.py --set <feature>:<param>=1
   ```

4. Add the constant in `soundblaster_g8/protocol.py`, the method in
   `driver.py`, and the feature name in `SUPPORTED_FEATURES`
   (`controller.py`) to enable it in the GUI.

`python tools/g8_probe.py --monitor` shows decoded notifications live,
which helps spot parameter identifiers.

To add a sound mode (new EQ/acoustic-engine preset): capture traffic
while the Creative application applies **a single** mode (same procedure
as above), drop the `.pcapng` into the captures folder, then regenerate
`soundblaster_g8/sound_modes.py`:

```bash
python tools/extract_sound_modes.py --input /path/to/the/captures/folder
```

## Translations

The interface's English/French text lives in gettext catalogs under
`soundblaster_g8/locale/<lang>/LC_MESSAGES/soundblaster_g8.po`. After
editing a `.po` file, recompile the catalogs:

```bash
python tools/compile_translations.py
```

The compiled `.mo` files are build artifacts (gitignored), regenerated
from the `.po` sources. Adding a new
`locale/<xx>/LC_MESSAGES/soundblaster_g8.po` (and compiling it) makes that
language show up automatically in the GUI's language selector on the next
launch.

## Project structure

```
OpenCreativeApp/
├── main.py                      # GUI entry point
├── tools/g8_probe.py            # diagnostic / reverse-engineering CLI
├── tools/extract_sound_modes.py # generates sound_modes.py from pcap captures
├── tools/compile_translations.py # compiles .po translation catalogs to .mo
├── udev/99-soundblaster-g8.rules
└── soundblaster_g8/
    ├── hidbackend.py            # hidapi backend selection (only platform-specific code)
    ├── protocol.py               # frame encoding/decoding (no I/O)
    ├── sound_modes.py           # generated sound modes (see extract_sound_modes.py)
    ├── driver.py                 # HID I/O (hidapi)
    ├── controller.py             # business logic + events
    ├── locale/                  # EN/FR translation catalogs (.po/.mo)
    └── gui/
        ├── main_window.py
        ├── eq_panel.py
        └── i18n.py               # translation loader/API
```

## Architecture

- **hidbackend.py**: the only platform-dependent module; chooses
  `hidraw` / `libusb` / IOKit and exposes `enumerate()`, `open_path()`,
  `backend_name()`, `provides_usage_page()`
- **protocol.py**: pure layer (framing, opcodes, TLV, padding), testable
  without hardware via `--selftest`
- **driver.py**: HID interface selection, unified transport (SET_REPORT
  64 B), ACK wait and verification, reconnection after a USB reset, state
  cache fed by notifications. All I/O is serialized by a lock (hidapi
  handles aren't thread-safe)
- **controller.py**: business logic; the `set_*` methods return a boolean
  indicating whether the card confirmed the command; `reconnecting` event
- **gui/**: Tkinter; commands run in a worker thread and the switch is
  resynchronized to the real hardware state on return; `i18n.py` provides
  the English/French translation catalogs and the live language switch

## License

MIT
