"""
ALSA fix for the Sound Blaster G8's microphone on Linux.

The ``snd-usb-audio`` kernel driver initializes the ALSA "PCM Capture
Source" control to ``Line In`` instead of ``External Mic``: the microphone
therefore picks up nothing until the source is changed manually
(alsamixer/pavucontrol), on every card restart.

This module re-applies the fix on application startup. There's also an
independent system-level fix (udev rule + script, ``alsa-fix/`` folder at
the repo root) that applies even without launching the app: the two
mechanisms are redundant for safety.

Card discovery via ``/proc/asound/card*/usbid`` (provided by the kernel,
never localized) rather than by parsing ``aplay -l``'s output, which is
localized (e.g. ``carte 1 : ...`` in French instead of ``card 1: ...``) and
makes matching by card name unreliable.

On a PipeWire/PulseAudio desktop, :func:`ensure_microphone_port` also moves
the G8's source onto the microphone port that ``alsa-fix/acp/`` adds: a
``Line In`` route remembered by WirePlumber from before that profile was
installed wins over the new port's priority, and the sound server then writes
``Line In`` back on every resume.

Control targeting by name (``amixer sset 'PCM Capture Source' ...``) rather
than by ``numid``, which can be renumbered between driver/kernel versions.
"""

from __future__ import annotations

import glob
import json
import os
import platform
import subprocess
import time
from typing import Optional

CAPTURE_SOURCE_CONTROL = "PCM Capture Source"
CAPTURE_SOURCE_TARGET = "External Mic"

AMIXER_TIMEOUT_S = 3.0

#: Sound server port names, from ``alsa-fix/acp/`` and the stock
#: ``paths/analog-input-linein.conf``.
MIC_PORT = "analog-input-external-mic"
LINE_IN_PORT = "analog-input-linein"

#: How long the card must have been enumerated before its mixer may be
#: written to. Writing sooner knocks it out of Direct Mode: measured on
#: hardware, a write 17 ms after the card registers reverts Direct Mode within
#: a second or two, the identical write 5 s later leaves it alone. Toggling
#: Direct Mode re-enumerates the card, which is what makes this reachable.
SETTLE_DELAY_S = 5.0


def _log(message: str) -> None:
    print(f"[ALSAFix] {message}")


def find_card_index(vendor_id: int, product_id: int) -> Optional[int]:
    """Finds the ALSA card index matching the given VID:PID.

    Reads ``/proc/asound/card*/usbid`` (e.g. ``041e:329b``): unlike
    ``aplay -l``, this file is never localized.
    """
    target = f"{vendor_id:04x}:{product_id:04x}"
    for usbid_path in sorted(glob.glob("/proc/asound/card*/usbid")):
        try:
            with open(usbid_path, "r", encoding="ascii") as f:
                content = f.read().strip()
        except OSError:
            continue
        if content == target:
            # .../card<N>/usbid
            digits = usbid_path.split("/card", 1)[1].split("/", 1)[0]
            try:
                return int(digits)
            except ValueError:
                continue
    return None


def seconds_since_enumeration(vendor_id: int, product_id: int) -> Optional[float]:
    """Age of the card's current USB enumeration, in seconds.

    The kernel creates the device's sysfs directory when it enumerates it, and
    that directory's mtime keeps the timestamp. Checked against the kernel log
    on real hardware: 276 ms apart, which is ample for a 5 s threshold.

    Returns ``None`` if the card isn't on the bus or sysfs isn't readable
    (non-Linux, container without /sys): callers treat that as "unknown", not
    as "settled".
    """
    for vendor_path in glob.glob("/sys/bus/usb/devices/*/idVendor"):
        directory = os.path.dirname(vendor_path)
        try:
            with open(vendor_path, "r", encoding="ascii") as f:
                if int(f.read().strip(), 16) != vendor_id:
                    continue
            with open(f"{directory}/idProduct", "r", encoding="ascii") as f:
                if int(f.read().strip(), 16) != product_id:
                    continue
            return max(0.0, time.time() - os.stat(directory).st_mtime)
        except (OSError, ValueError):
            continue  # device unplugged mid-read, or unreadable attribute
    return None


def ensure_microphone_source(
    vendor_id: int,
    product_id: int,
    settle_delay: float = SETTLE_DELAY_S,
) -> bool:
    """Selects ``External Mic`` as the ALSA capture source.

    Does nothing (and never raises) outside Linux, if the ALSA card isn't
    found, if ``amixer`` is missing, or if the command fails: this fix is a
    "best effort" that must never prevent the application from starting.

    Also does nothing if the card enumerated less than ``settle_delay``
    seconds ago, because the write would drop it out of Direct Mode (see
    :data:`SETTLE_DELAY_S`). It *skips* rather than waits: this runs on the Tk
    thread from ``controller.connect()`` and must not stall startup. The udev
    rule in ``alsa-fix/`` covers that window - it can afford to sleep.
    """
    if platform.system() != "Linux":
        return False

    age = seconds_since_enumeration(vendor_id, product_id)
    if age is not None and age < settle_delay:
        _log(
            f"card enumerated {age:.1f}s ago and is still settling: fix "
            f"skipped (writing now would drop it out of Direct Mode)"
        )
        return False

    card_index = find_card_index(vendor_id, product_id)
    if card_index is None:
        _log("ALSA card not found (/proc/asound/card*/usbid): fix skipped")
        return False

    try:
        result = subprocess.run(
            [
                "amixer",
                "-c",
                str(card_index),
                "-q",
                "sset",
                CAPTURE_SOURCE_CONTROL,
                CAPTURE_SOURCE_TARGET,
            ],
            capture_output=True,
            text=True,
            timeout=AMIXER_TIMEOUT_S,
        )
    except FileNotFoundError:
        _log("'amixer' command not found (alsa-utils package missing): fix skipped")
        return False
    except subprocess.TimeoutExpired:
        _log(f"'amixer' didn't respond (card {card_index}): fix skipped")
        return False
    except OSError as exc:
        _log(f"'amixer' call failed (card {card_index}): {exc}")
        return False

    if result.returncode != 0:
        _log(
            f"failed to select capture source (card {card_index}): "
            f"{result.stderr.strip() or result.returncode}"
        )
        return False

    _log(f"capture source set to '{CAPTURE_SOURCE_TARGET}' (card {card_index})")
    return True


def _pactl(args: list[str]) -> Optional[str]:
    """Runs ``pactl``, returning its stdout or ``None`` on any failure."""
    try:
        result = subprocess.run(
            ["pactl", *args],
            capture_output=True,
            text=True,
            timeout=AMIXER_TIMEOUT_S,
        )
    except FileNotFoundError:
        return None  # no PulseAudio/PipeWire: amixer alone is the fix
    except (subprocess.TimeoutExpired, OSError) as exc:
        _log(f"'pactl {' '.join(args)}' failed: {exc}")
        return None
    if result.returncode != 0:
        _log(f"'pactl {' '.join(args)}' failed: {result.stderr.strip() or result.returncode}")
        return None
    return result.stdout


def ensure_microphone_port(
    vendor_id: int,
    product_id: int,
    settle_delay: float = SETTLE_DELAY_S,
) -> bool:
    """Moves the G8's sound server source from Line In to the microphone port.

    Only acts when the source sits on ``Line In`` *and* offers the
    microphone port (i.e. the ``alsa-fix/`` card profile is installed): any
    other port is a choice the user made, and is left alone. Once switched,
    WirePlumber remembers the new route, so this normally fires only once.

    Same rules as :func:`ensure_microphone_source`: Linux only, never raises,
    and skipped while the card is settling - the port switch writes
    ``PCM Capture Source`` too.
    """
    if platform.system() != "Linux":
        return False

    age = seconds_since_enumeration(vendor_id, product_id)
    if age is not None and age < settle_delay:
        return False

    # JSON rather than the human-readable listing, which is localized.
    output = _pactl(["--format=json", "list", "sources"])
    if output is None:
        return False
    try:
        sources = json.loads(output)
    except ValueError as exc:
        _log(f"unreadable 'pactl list sources' output: {exc}")
        return False

    vendor = f"0x{vendor_id:04x}"
    product = f"0x{product_id:04x}"
    switched = False
    for source in sources:
        properties = source.get("properties", {})
        if (
            properties.get("device.vendor.id") != vendor
            or properties.get("device.product.id") != product
            or source.get("active_port") != LINE_IN_PORT
        ):
            continue
        ports = {port.get("name") for port in source.get("ports", [])}
        if MIC_PORT not in ports:
            continue  # card profile not installed: nothing better to offer
        name = source.get("name", "")
        if _pactl(["set-source-port", name, MIC_PORT]) is not None:
            _log(f"source '{name}' moved from Line In to the microphone port")
            switched = True
    return switched
