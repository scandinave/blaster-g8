# Sound Blaster G8 — ALSA Fix

Automatic fix for the microphone ("External Mic") not working on Linux at
startup.

The `snd-usb-audio` kernel driver doesn't initialize the correct default
capture source for the G8: the ALSA "PCM Capture Source" control starts on
`Line In` instead of `External Mic`. The microphone therefore doesn't work
until the source is changed manually (alsamixer/pavucontrol), on every
restart of the card.

Same bug, same fix as on the [SoundBlasterX G6](../../linuxblaster_control/alsa-fix)
(same chip/same ALSA control layout) — this folder is a port of it.

## The fix

A udev rule detects the G8's ALSA card appearing and automatically runs a
small script that selects `External Mic` as the capture source
(`PCM Capture Source`).

Works on any distro. Only `alsa-utils` (`amixer`) is required, already
installed on virtually every Linux system with sound.

Unlike the G6 script, this one **doesn't mute** the other capture inputs
(Line In / S/PDIF In / What U Hear): it just selects the correct source.

Two deliberate differences from the G6 script, for extra robustness:

1. **Card discovery**: reads `/proc/asound/card*/usbid` (provided by the
   kernel, never localized) rather than parsing `aplay -l`'s output, which
   is localized (`carte 1 : ...` in French instead of `card 1: ...`) — the
   G6 script breaks silently on any non-English-speaking machine.
2. **Control targeting**: by name (`amixer sset 'PCM Capture Source'
   'External Mic'`) rather than by `numid` (`cset numid=29 ...`), which can
   be renumbered between driver/kernel versions.

The `soundblaster_g8` application (GUI) also re-applies this fix on every
startup (`soundblaster_g8/alsa_fix.py`), independently of this folder — the
two mechanisms are redundant for safety: this one works even if the app is
never launched.

## Installation

```bash
sudo ./install.sh
```

Replug the card (or trigger `sudo udevadm trigger --subsystem-match=sound`)
and the microphone works.

## Uninstallation

```bash
sudo ./install.sh --uninstall
```

## How it works

```
G8 plugged in
  → the kernel loads snd-usb-audio
    → ALSA registers the sound card
      → udev sees the SUBSYSTEM=="sound" event with the G8's USB ID
        → runs the fix script
          → amixer selects "External Mic" as the capture source
```

No service, no daemon, no polling. Just a one-shot script triggered by
hardware detection.
