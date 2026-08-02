"""
HID backend selection, unified across macOS / Linux / Windows.

This is the **only** module in the project that depends on the platform: the
driver must not import ``hid`` or ``hidraw`` directly.

On Linux, ``pip install hidapi`` installs two Python modules:

* ``hid``    : **libusb** backend (the one shipped by the binary *wheels*;
  it detaches the ``usbhid`` kernel driver for the duration of the access
  and **does not populate** ``usage_page`` in ``hid_enumerate``).
* ``hidraw`` : **hidraw** backend (no kernel driver detachment,
  ``usage_page`` read from the report descriptor exposed via sysfs). Only
  present if hidapi was compiled with ``HIDAPI_WITH_HIDRAW=1``.

Both modules expose the same Python API (``hidraw.pyx`` is a copy of
``hid.pyx`` in cython-hidapi), hence the ability to swap them.

Preference order:

* Linux   : ``hidraw`` then ``hid`` (libusb).
* macOS   : ``hid`` (IOKit, the only one available).
* Windows : ``hid`` (setupapi, the only one available).

The chosen backend is logged on first call: it's the most useful piece of
information when behavior diverges between two Linux machines.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass
from typing import Any, Iterable, Optional

_SYSTEM = platform.system()


@dataclass(frozen=True)
class BackendInfo:
    """Result of the backend selection."""

    module: Any
    name: str
    provides_usage_page: bool

    def __str__(self) -> str:  # pragma: no cover - debug display
        usage = "yes" if self.provides_usage_page else "no"
        return f"{self.name} (usage_page enumerated: {usage})"


_backend_cache: Optional[BackendInfo] = None
_logged = False


def _log(message: str) -> None:
    print(f"[hidbackend] {message}")


def _module_ok(mod: Any) -> bool:
    return mod is not None and hasattr(mod, "enumerate") and hasattr(mod, "device")


def _select() -> BackendInfo:
    if _SYSTEM == "Linux":
        try:
            import hidraw  # type: ignore
        except ImportError:
            hidraw = None  # type: ignore
        try:
            import hid  # type: ignore
        except ImportError:
            hid = None  # type: ignore

        # hidraw first: it populates usage_page and doesn't detach the kernel
        # driver, which avoids cutting off the card's audio/media devices
        # while talking to the control channel.
        if _module_ok(hidraw):
            return BackendInfo(module=hidraw, name="hidraw", provides_usage_page=True)
        if _module_ok(hid):
            return BackendInfo(module=hid, name="libusb", provides_usage_page=False)
        raise ImportError(
            "No HID backend available. Install hidapi "
            "('pip install hidapi'); to get the hidraw backend: "
            "'HIDAPI_WITH_HIDRAW=1 pip install --no-binary :all: hidapi'."
        )

    try:
        import hid  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "Module 'hid' (hidapi) not found: 'pip install hidapi'."
        ) from exc

    return BackendInfo(
        module=hid,
        name="iokit" if _SYSTEM == "Darwin" else "windows",
        provides_usage_page=True,
    )


def get_backend() -> BackendInfo:
    """Returns the HID backend to use, cached on first call."""
    global _backend_cache, _logged
    if _backend_cache is None:
        _backend_cache = _select()
    if not _logged:
        _logged = True
        _log(f"platform {_SYSTEM}, backend selected: {_backend_cache}")
    return _backend_cache


def is_available() -> bool:
    """``True`` if a usable HID backend is installed."""
    try:
        get_backend()
    except ImportError as exc:
        _log(f"no HID backend: {exc}")
        return False
    return True


def backend_name() -> str:
    """Name of the selected backend: ``hidraw`` / ``libusb`` / ``iokit`` / ``windows``."""
    try:
        return get_backend().name
    except ImportError:
        return "none"


def provides_usage_page() -> bool:
    """``False`` with libusb: ``hid_enumerate`` doesn't populate ``usage_page`` there.

    The driver uses this to know that interface selection must fall back to
    ``interface_number`` without that being considered abnormal.
    """
    try:
        return get_backend().provides_usage_page
    except ImportError:
        return False


def enumerate(vendor_id: int = 0, product_id: int = 0) -> list[dict]:
    """The selected backend's ``hid_enumerate``, as a list of dicts."""
    entries: Iterable[dict] = get_backend().module.enumerate(vendor_id, product_id)
    return list(entries)


def open_path(path: bytes) -> Any:
    """Opens a HID device by its ``path`` and returns the backend's handle."""
    device = get_backend().module.device()
    device.open_path(path)
    return device


def reset_cache() -> None:
    """Clears the cache (useful for tests)."""
    global _backend_cache, _logged
    _backend_cache = None
    _logged = False
