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

Two layers, installed together by `install.sh`:

1. An **ALSA card profile** that gives the card a microphone port, so that
   PipeWire/PulseAudio selects `External Mic` on its own and stops overwriting
   the setting. This is what makes the fix *hold* — see
   [the sound server writes too](#the-sound-server-writes-too-and-why-amixer-alone-loses).
2. A **udev rule + script** that selects `External Mic` with `amixer`,
   covering systems with no PipeWire/PulseAudio at all, and the window before
   the sound server has configured the card.

The udev rule detects the G8's ALSA card appearing and automatically runs a
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

## The sound server writes too, and why amixer alone loses

The `amixer` fix above is not enough on a PipeWire (or PulseAudio) desktop.
Measured on hardware — the script runs, succeeds, and the setting is undone
anyway:

| Observation | Command |
| --- | --- |
| the udev script runs at boot and succeeds | `journalctl -t soundblaster-g8-alsa-fix` → `Successfully set capture source to 'External Mic' on card 3` |
| the ALSA control really is on the mic | `amixer -c 3 sget 'PCM Capture Source'` → `Item0: 'External Mic'` |
| but the sound server routes the input to the line input | `pactl list sources` → `Active Port: analog-input-linein` |
| because the card has **no microphone port at all** | `pactl list cards` → the only analog input port is `analog-input-linein` |

The card profile (ACP) that PipeWire and PulseAudio share builds a card's ports
from mixer *path* files. `paths/analog-input-mic.conf` maps only the `Mic` and
`Mic-In/Mic Array` items of the `PCM Capture Source` enumeration; the G8's item
is named **`External Mic`**, which matches nothing, so no microphone port is
built. `paths/analog-input-linein.conf` does map `Line In` — so the line input
becomes the card's only analog input port, gets selected, and the sound server
writes `PCM Capture Source` back to `Line In` **every time it applies that
route**: card creation, source resume, WirePlumber restart, profile change.

Whoever writes last wins, and it isn't us. That is the whole symptom: the fix
appears not to work, and launching the GUI "repairs" it — because the GUI
replays `amixer` after the sound server.

So instead of racing it, teach it. Two files add the missing port:

- `acp/analog-input-external-mic.conf` → `/usr/share/alsa-card-profile/mixer/paths/`
  maps `[Option PCM Capture Source:External Mic]` to a microphone port, at
  priority 88 (above `analog-input-mic`'s 87 and `analog-input-linein`'s 81, so
  it is the default input).
- `acp/soundblaster-g8.conf` → `/usr/share/alsa-card-profile/mixer/profile-sets/`
  is `default.conf` plus that path in the analog mapping's `paths-input`.

`91-soundblaster-g8-acp.rules` binds the profile set to this card only, through
the `ENV{ACP_PROFILE_SET}` udev property that `default.conf`'s own header
documents (and that `/usr/lib/udev/rules.d/90-pipewire-alsa.rules` uses for its
quirks). Every other card keeps the stock profile.

The result: the G8 shows a real *Microphone* input in the desktop's sound
settings, the sound server selects it and writes `External Mic` itself, and
WirePlumber remembers the choice across reboots.

Both file names are our own, so no package owns them and a pipewire update
neither removes nor overwrites them. Re-check them if the ACP format ever
changes.

**If the input stays on "Line In" after installing**: a previous route is
remembered in `~/.local/state/wireplumber/default-routes`. Pick *Microphone*
once in the sound settings — that replaces it.

## Direct Mode, and why this fix has to wait

Writing to the G8's ALSA mixer while it is still settling after a
re-enumeration knocks it out of Direct Mode. Measured on hardware:

| Write happens | Direct Mode |
| --- | --- |
| 17 ms after the ALSA card registers | reverts within a second or two |
| 5 s after | unaffected |
| 2 min after | unaffected |

This matters here because **toggling Direct Mode re-enumerates the card** —
the very event that triggers this script. Before the delay was added, enabling
Direct Mode reverted on its own every time, whether toggled from the app or
from the card's physical button.

Hence `SETTLE_DELAY` (5 s) in the script, and the matching
`SETTLE_DELAY_S` guard in `soundblaster_g8/alsa_fix.py`. The app *skips* the
fix instead of waiting, since it runs on the UI thread at startup; the udev
script covers that window.

### The other writer: `alsactl restore`

`alsa-utils` ships `/usr/lib/udev/rules.d/90-alsa-restore.rules`, which runs
`alsactl restore` the moment a card registers and rewrites its entire saved
mixer state. That breaks Direct Mode on its own, independently of this script
— confirmed by disabling each rule in turn.

It cannot be delayed: udev runs `RUN+=` programs unconditionally, and no rule
file can reorder or postpone another's. Removing the card's section from
`/var/lib/alsa/asound.state` does not work either — `alsactl` then falls back
to `init`, which writes too (tested).

So `install.sh` offers to install `90-alsa-restore.rules` from this folder into
`/etc/udev/rules.d/`, shadowing the alsa-utils copy with an identical one that
skips `041e:329b`. It is **opt-in**, and `--uninstall` removes it again.
Without it, Direct Mode will not hold.

Trade-off: the G8's mixer levels are no longer restored at boot by ALSA. On a
desktop, PipeWire/WirePlumber owns volumes anyway. Re-check the copy if
alsa-utils ever updates its own rule — it is verbatim from 1.2.9-1ubuntu5
(2024-04-07).

### The card has two USB inputs

The G8 exposes a **different mixer control set depending on which of its two
USB inputs are connected** — 19 controls in one configuration, 29 in the other,
with different `numid`s for the same control names. Two consequences:

- Always target controls **by name**, never by `numid`. The script and
  `alsa_fix.py` already do.
- If the second input is plugged into another machine, **that machine breaks
  Direct Mode from its end** — its own `alsactl restore`, its own audio stack,
  asynchronously and invisibly from here. Measured: with everything on this
  side fixed, Direct Mode held with the second input unplugged and dropped with
  it plugged into another Linux box. Fixing this side only fixes this side; the
  other machine needs the same treatment.

### What is *not* a problem

PipeWire/WirePlumber probes the card ~50 ms after it re-enumerates — visible as
`Capture Channel Map` flicking `0,0 -> 3,4 -> 0,0`. That was the obvious
suspect and it is **harmless**: Direct Mode survives it. Only writes to mixer
*controls* matter. Worth recording, because it costs an hour to re-suspect.

## Installation

```bash
sudo ./install.sh
```

Replug the card (or trigger `sudo udevadm trigger --subsystem-match=sound`)
and the microphone works.

The sound server only reads the card profile when it builds the card, so to
pick up the new microphone port without replugging, restart it as your own
user:

```bash
systemctl --user restart wireplumber
```

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
        │
        ├→ sets ACP_PROFILE_SET=soundblaster-g8.conf on the card
        │    → PipeWire/PulseAudio builds the card from our profile set
        │      → finds a microphone port for "External Mic" and selects it
        │        → and keeps writing that, every time it applies the route
        │
        └→ runs the fix script
             → waits 5 s for the card to settle (else Direct Mode drops)
               → amixer selects "External Mic" as the capture source
```

No service, no daemon, no polling. A udev property the sound server reads on
its own, and a one-shot script triggered by hardware detection.
