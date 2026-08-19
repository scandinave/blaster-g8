"""Bootstrap Icons for the Tkinter interface: tinting, caching, lookup.

The application refers to icons by *semantic* names (``"direct"``,
``"equalizer"``, ``"microphone"``…), which the widgets and their data tables
(``main_window.TOGGLE_DEFS``, ``sidebar.MENU_DEFS``, ``eq_panel``) use
unchanged; :data:`BOOTSTRAP_NAMES` is the single place mapping them to the
vendored Bootstrap Icons.

Tk has no SVG support, so the glyphs are pre-rasterized into 8-bit alpha masks
by ``tools/build_icons.py`` (see ``icon_data.py``). The colour is *not* baked
in: a widget's icon changes colour with its state - normal, hovered, selected,
disabled - so :func:`get` composes a small RGBA PNG in memory, tinted to the
requested colour, and hands it to Tk. Encoding a PNG by hand is a dozen lines
of zlib and CRC32 and keeps the application free of any imaging dependency;
shipping pre-tinted files instead would multiply the assets by the number of
colours and freeze the palette.

Every image is cached by ``(name, size, colour)``. That keeps the cost to one
encode per icon-state actually displayed, and - just as importantly - holds a
reference to each ``PhotoImage``: a Tk image with no live Python reference is
garbage-collected and vanishes from the widget that drew it.
"""

from __future__ import annotations

import base64
import struct
import tkinter as tk
import zlib
from typing import Optional

from .icon_data import MASKS, SIZES

#: Semantic icon name -> Bootstrap Icons name (files under
#: ``assets/bootstrap-icons/``).
BOOTSTRAP_NAMES = {
    "direct": "soundwave",
    "scout": "crosshair",
    "voice": "chat-square-dots",
    "equalizer": "sliders",
    "decoder": "activity",
    "reset": "arrow-counterclockwise",
    "device": "pci-card-sound",
    "playback": "play-fill",
    "recording": "record-circle",
    "settings": "gear-fill",
    "speaker": "volume-up-fill",
    "microphone": "mic-fill",
    "led": "lightbulb-fill",
    "energy_saving": "leaf-fill",
}

#: (name, size, colour) -> PhotoImage.
_CACHE: dict[tuple[str, int, str], tk.PhotoImage] = {}

#: Names already reported as missing, so a widget redrawing on every hover
#: doesn't flood the console.
_WARNED: set[str] = set()


def _log(message: str) -> None:
    print(f"[Icons] {message}")


def _parse_color(color: str) -> tuple[int, int, int]:
    """Turns ``#rrggbb`` (or ``#rgb``) into an (r, g, b) triple."""
    value = color.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _png(mask: bytes, size: int, rgb: tuple[int, int, int]) -> bytes:
    """Builds an RGBA PNG of ``size``x``size`` from an alpha mask."""
    red, green, blue = rgb
    pixel = bytes((red, green, blue))
    raw = bytearray()
    for y in range(size):
        raw.append(0)  # per-scanline filter type: none
        row = mask[y * size:(y + 1) * size]
        for alpha in row:
            raw += pixel
            raw.append(alpha)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        # 8 bits per channel, colour type 6 (RGBA), no interlacing.
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def get(name: str, size: int, color: str) -> Optional[tk.PhotoImage]:
    """Returns the icon ``name`` at ``size`` px, tinted ``color``.

    ``name`` is a semantic name from :data:`BOOTSTRAP_NAMES`. Returns ``None``
    (after logging once) for an unknown name or an unavailable size, rather
    than raising: a missing icon must never take the window down, and the
    calling widget simply draws without it.

    A Tk root window must exist before the first call, as for any
    ``PhotoImage``.
    """
    key = (name, size, color)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    bootstrap_name = BOOTSTRAP_NAMES.get(name)
    if bootstrap_name is None:
        if name not in _WARNED:
            _WARNED.add(name)
            _log(f"unknown icon '{name}' (see BOOTSTRAP_NAMES)")
        return None

    by_size = MASKS.get(bootstrap_name)
    if by_size is None or size not in by_size:
        warn_key = f"{name}@{size}"
        if warn_key not in _WARNED:
            _WARNED.add(warn_key)
            _log(
                f"no {size}px mask for '{name}' ({bootstrap_name}); "
                f"available: {', '.join(str(s) for s in SIZES)} "
                f"- rerun tools/build_icons.py to add it"
            )
        return None

    photo = tk.PhotoImage(
        data=base64.b64encode(_png(by_size[size], size, _parse_color(color)))
    )
    _CACHE[key] = photo
    return photo
