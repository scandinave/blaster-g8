# Project structure and architecture

## Interface notes

The interface is bilingual (English/French), with a language selector in
the header; the choice persists across restarts.

The pictograms are [Bootstrap Icons](https://icons.getbootstrap.com) (MIT),
**bundled in the repository** — nothing is fetched over the network at
runtime. The `.svg` under `assets/bootstrap-icons/` are build sources:
`tools/build_icons.py` rasterizes them into alpha masks
(`soundblaster_g8/gui/icon_data.py`, generated and committed) that the GUI
tints on the fly to match each widget's state. Only regenerating them needs
`cairosvg` (`pip install -e '.[build]'`).

A sidebar on the left holds the application's menu — **Devices** (the
card's controls) and **Settings** — and, at its foot, two sliders for the
PC's own output and microphone volume. Those two act on the system's
default devices (via `pactl` on Linux, `osascript` on macOS), not on the
card's registers, and follow changes made elsewhere in the desktop.

## Project structure

```
OpenCreativeApp/
├── main.py                      # GUI entry point
├── assets/bootstrap-icons/      # vendored Bootstrap Icons .svg (build sources)
├── tools/g8_probe.py            # diagnostic / reverse-engineering CLI
├── tools/extract_sound_modes.py # generates sound_modes.py from pcap captures
├── tools/extract_crystalvoice_presets.py # generates crystalvoice_presets.py from pcap captures
├── tools/compile_translations.py # compiles .po translation catalogs to .mo
├── tools/build_icons.py         # rasterizes the .svg icons into gui/icon_data.py
├── udev/99-soundblaster-g8.rules
└── soundblaster_g8/
    ├── hidbackend.py            # hidapi backend selection (platform-specific)
    ├── system_volume.py         # PC volume/microphone (pactl on Linux, osascript on macOS)
    ├── protocol.py               # frame encoding/decoding (no I/O)
    ├── sound_modes.py           # generated sound modes (see extract_sound_modes.py)
    ├── crystalvoice_presets.py  # generated Voice Morph / mic-EQ presets
    ├── driver.py                 # HID I/O (hidapi)
    ├── controller.py             # business logic + events
    ├── locale/                  # EN/FR translation catalogs (.po/.mo)
    └── gui/
        ├── main_window.py
        ├── sidebar.py            # left navigation menu + PC volume sliders
        ├── icons.py              # Bootstrap Icons: tinting + PhotoImage cache
        ├── icon_data.py          # generated alpha masks (see build_icons.py)
        ├── eq_panel.py
        ├── crystalvoice_panel.py
        ├── decoder_panel.py
        └── i18n.py               # translation loader/API
```

## Architecture

- **hidbackend.py**: chooses `hidraw` / `libusb` / IOKit and exposes
  `enumerate()`, `open_path()`, `backend_name()`,
  `provides_usage_page()`
- **system_volume.py**: the PC's own output/microphone volume (the
  sidebar sliders), driving the system's *default* device through
  `pactl` on Linux and `osascript` on macOS; best effort, and simply
  reports itself unavailable — greying the sliders out — when neither is
  usable
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
