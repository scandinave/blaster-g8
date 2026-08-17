# Contributing to the reverse engineering

## Command-line tool

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

## Adding a feature

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

## Adding a sound mode

To add a sound mode (new EQ/acoustic-engine preset): capture traffic
while the Creative application applies **a single** mode (same procedure
as above), drop the `.pcapng` into the captures folder, then regenerate
`soundblaster_g8/sound_modes.py`:

```bash
python tools/extract_sound_modes.py --input /path/to/the/captures/folder
```

See [protocol.md](protocol.md#sound-mode-type-0x12-confirmed) for the
underlying frame format.

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
