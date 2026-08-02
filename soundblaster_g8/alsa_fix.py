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

Control targeting by name (``amixer sset 'PCM Capture Source' ...``) rather
than by ``numid``, which can be renumbered between driver/kernel versions.
"""

from __future__ import annotations

import glob
import platform
import subprocess
from typing import Optional

CAPTURE_SOURCE_CONTROL = "PCM Capture Source"
CAPTURE_SOURCE_TARGET = "External Mic"

AMIXER_TIMEOUT_S = 3.0


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


def ensure_microphone_source(vendor_id: int, product_id: int) -> bool:
    """Selects ``External Mic`` as the ALSA capture source.

    Does nothing (and never raises) outside Linux, if the ALSA card isn't
    found, if ``amixer`` is missing, or if the command fails: this fix is a
    "best effort" that must never prevent the application from starting.
    """
    if platform.system() != "Linux":
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
