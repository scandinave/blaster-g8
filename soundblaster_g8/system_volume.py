"""
System volume control (PC output and microphone), used by the sidebar sliders.

Targets the *default* output/input device of the system, not the Sound Blaster
G8 specifically: the sliders are the PC's volume, wherever the sound currently
goes. Switching the default device in the desktop's sound settings therefore
moves what the sliders act on, with no action needed here.

One public API, two implementations picked at import time from
``platform.system()`` (same convention as ``driver.PLATFORM`` and
``hidbackend``):

* Linux : ``pactl`` (PulseAudio, and PipeWire through its pulse layer).
* macOS : ``osascript`` (AppleScript ``get volume settings`` / ``set volume``).

On Linux, when the default device *is* the G8, a volume change goes straight to
the card's ALSA mixer (its sink carries ``HW_VOLUME_CTRL``) - hence
:func:`default_device_is_g8`, which lets the GUI hold a write back while the
card is still settling after a re-enumeration (``alsa_fix.SETTLE_DELAY_S``).

Any other platform reports itself unavailable, which just leaves the sliders
greyed out. Like ``alsa_fix``, this module is "best effort" and never raises:
every external-command failure is logged and turned into ``None``/``False``, so
a missing or broken sound server can't stop the application from running.

``pactl``'s human-readable output is localized (``Sourdine : non`` in French),
so the Linux backend reads ``--format=json`` exclusively.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import threading
from typing import Callable, Optional

PLATFORM = platform.system()

#: Volume targets, as accepted by get_volume/set_volume.
OUTPUT = "output"
INPUT = "input"

COMMAND_TIMEOUT_S = 2.0

#: macOS has no equivalent of ``pactl subscribe``: the watcher re-reads the
#: volumes on this period and only calls back when a value actually changed.
POLL_INTERVAL_S = 2.0

#: Linux: ``pactl subscribe`` fires several events per volume change (and
#: dozens while a stream starts). Coalesce them before re-reading.
DEBOUNCE_S = 0.15

#: Substring identifying the G8 in a PulseAudio device name, e.g.
#: ``alsa_output.usb-Creative_Technology_Ltd_Sound_Blaster_G8_USB-1_...``.
_G8_DEVICE_MARKER = "Sound_Blaster_G8"


def _log(message: str) -> None:
    print(f"[SystemVolume] {message}")


def _run(args: list[str]) -> Optional[str]:
    """Runs a short command and returns its stdout, or ``None`` on any failure."""
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=COMMAND_TIMEOUT_S,
        )
    except FileNotFoundError:
        _log(f"'{args[0]}' command not found: volume control unavailable")
        return None
    except subprocess.TimeoutExpired:
        _log(f"'{' '.join(args)}' didn't respond within {COMMAND_TIMEOUT_S}s")
        return None
    except OSError as exc:
        _log(f"'{' '.join(args)}' failed: {exc}")
        return None

    if result.returncode != 0:
        _log(f"'{' '.join(args)}' failed: {result.stderr.strip() or result.returncode}")
        return None
    return result.stdout


class _Watcher:
    """Background thread notifying the caller of externally-made volume changes.

    Started by :func:`start_watch`, stopped by :func:`stop_watch`. The callback
    runs on this thread: Tk callers must bounce it back with ``after(0, ...)``.
    """

    def __init__(self, callback: Callable[[], None]):
        self._callback = callback
        self._stop = threading.Event()
        self._process: Optional[subprocess.Popen] = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        process = self._process
        if process is not None:
            try:
                process.terminate()
            except OSError:
                pass

    def _run(self) -> None:  # pragma: no cover - background thread
        raise NotImplementedError

    def _notify(self) -> None:
        if self._stop.is_set():
            return
        try:
            self._callback()
        except Exception as exc:  # pragma: no cover - defensive, mirrors i18n/controller
            _log(f"Listener error: {exc}")


# ----------------------------------------------------------------------
# Linux backend: pactl (PulseAudio / PipeWire)
# ----------------------------------------------------------------------

#: (pactl object kind, default-device subcommand, set-volume subcommand,
#: default-device shorthand) per target.
_PACTL_TARGETS = {
    OUTPUT: ("sinks", "get-default-sink", "set-sink-volume", "@DEFAULT_SINK@"),
    INPUT: ("sources", "get-default-source", "set-source-volume", "@DEFAULT_SOURCE@"),
}


def _pactl_available() -> bool:
    return shutil.which("pactl") is not None and _run(["pactl", "info"]) is not None


def _pactl_default_device(kind: str) -> Optional[str]:
    _objects, default_cmd, _set_cmd, _shorthand = _PACTL_TARGETS[kind]
    output = _run(["pactl", default_cmd])
    if output is None:
        return None
    name = output.strip()
    return name or None


def _pactl_get_volume(kind: str) -> Optional[tuple[int, bool]]:
    name = _pactl_default_device(kind)
    if name is None:
        return None

    objects = _PACTL_TARGETS[kind][0]
    output = _run(["pactl", "--format=json", "list", objects])
    if output is None:
        return None

    try:
        entries = json.loads(output)
    except ValueError as exc:
        _log(f"unreadable 'pactl list {objects}' output: {exc}")
        return None

    for entry in entries:
        if entry.get("name") != name:
            continue
        channels = entry.get("volume") or {}
        percents = []
        for channel in channels.values():
            raw = str(channel.get("value_percent", "")).rstrip("%")
            try:
                percents.append(int(raw))
            except ValueError:
                continue
        if not percents:
            _log(f"no readable volume for '{name}'")
            return None
        # Channels can differ (balance): show the loudest, like desktop mixers.
        return max(percents), bool(entry.get("mute"))

    _log(f"default device '{name}' missing from 'pactl list {objects}'")
    return None


def _pactl_set_volume(kind: str, percent: int) -> bool:
    _objects, _default_cmd, set_cmd, shorthand = _PACTL_TARGETS[kind]
    return _run(["pactl", set_cmd, shorthand, f"{percent}%"]) is not None


def _pactl_default_device_is_g8(kind: str) -> bool:
    name = _pactl_default_device(kind)
    return name is not None and _G8_DEVICE_MARKER in name


class _PactlWatcher(_Watcher):
    """Follows ``pactl subscribe``, debouncing its event storms.

    A single volume change produces a handful of events (measured: six per
    ``set-sink-volume``), so reading and notifying are split across two
    threads: the reader only raises a flag, and the notifier collapses
    everything raised within ``DEBOUNCE_S`` into one callback. Debouncing
    inside the read loop would not work - the extra lines simply pile up in the
    pipe while it sleeps, then fire one callback each.
    """

    def _run(self) -> None:  # pragma: no cover - background thread
        try:
            self._process = subprocess.Popen(
                ["pactl", "subscribe"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except (FileNotFoundError, OSError) as exc:
            _log(f"'pactl subscribe' couldn't start ({exc}): "
                 f"external volume changes won't be reflected")
            return

        changed = threading.Event()
        threading.Thread(target=self._read_events, args=(changed,), daemon=True).start()

        while not self._stop.is_set():
            if not changed.wait(POLL_INTERVAL_S):
                continue  # nothing happened; loop back to re-check _stop
            if self._stop.wait(DEBOUNCE_S):
                break
            # Cleared *before* notifying: an event arriving while the callback
            # runs sets it again and is picked up on the next pass.
            changed.clear()
            self._notify()

    def _read_events(self, changed: threading.Event) -> None:  # pragma: no cover - background thread
        stdout = self._process.stdout if self._process is not None else None
        if stdout is None:
            return
        for line in stdout:
            if self._stop.is_set():
                break
            # Event lines name the object kind, e.g. "Event 'change' on sink
            # #61". Server/client/stream events are noise for our purposes.
            if "sink" in line or "source" in line:
                changed.set()


# ----------------------------------------------------------------------
# macOS backend: osascript (AppleScript)
# ----------------------------------------------------------------------

#: (property of "get volume settings", "set volume" clause) per target.
_OSASCRIPT_TARGETS = {
    OUTPUT: ("output volume", "output volume"),
    INPUT: ("input volume", "input volume"),
}


def _osascript(script: str) -> Optional[str]:
    output = _run(["osascript", "-e", script])
    return None if output is None else output.strip()


def _osascript_available() -> bool:
    return (
        shutil.which("osascript") is not None
        and _osascript_get_volume(OUTPUT) is not None
    )


def _osascript_get_volume(kind: str) -> Optional[tuple[int, bool]]:
    prop = _OSASCRIPT_TARGETS[kind][0]
    raw = _osascript(f"{prop} of (get volume settings)")
    if raw is None:
        return None
    try:
        percent = int(raw)
    except ValueError:
        # "missing value": the default device exposes no software volume.
        _log(f"'{prop}' unavailable on the default device ({raw!r})")
        return None
    if percent < 0:
        # AppleScript reports -1 for input devices with no software gain
        # control (common with USB microphones).
        _log(f"'{prop}' unavailable on the default device (reported {percent})")
        return None

    # Only the output has a mute flag in AppleScript; an input is never
    # reported as muted, so treat it as unmuted.
    muted = False
    if kind == OUTPUT:
        raw_muted = _osascript("output muted of (get volume settings)")
        muted = raw_muted == "true"
    return min(100, percent), muted


def _osascript_set_volume(kind: str, percent: int) -> bool:
    clause = _OSASCRIPT_TARGETS[kind][1]
    return _osascript(f"set volume {clause} {percent}") is not None


def _osascript_default_device_is_g8(_kind: str) -> bool:
    # The Direct Mode settle guard this feeds is Linux-only (it exists because
    # of ALSA mixer writes): nothing to protect here.
    return False


class _PollingWatcher(_Watcher):
    """Re-reads both volumes periodically, notifying only on a real change.

    macOS fallback: AppleScript offers no volume-change notification.
    """

    def _run(self) -> None:  # pragma: no cover - background thread
        previous = (get_volume(OUTPUT), get_volume(INPUT))
        while not self._stop.wait(POLL_INTERVAL_S):
            current = (get_volume(OUTPUT), get_volume(INPUT))
            if current != previous:
                previous = current
                self._notify()


# ----------------------------------------------------------------------
# Backend selection
# ----------------------------------------------------------------------

if PLATFORM == "Linux":
    _available = _pactl_available
    _get_volume = _pactl_get_volume
    _set_volume = _pactl_set_volume
    _default_device_is_g8 = _pactl_default_device_is_g8
    _watcher_class: Optional[type[_Watcher]] = _PactlWatcher
elif PLATFORM == "Darwin":
    _available = _osascript_available
    _get_volume = _osascript_get_volume
    _set_volume = _osascript_set_volume
    _default_device_is_g8 = _osascript_default_device_is_g8
    _watcher_class = _PollingWatcher
else:  # Windows and anything else: no backend, sliders stay disabled.
    _available = lambda: False  # noqa: E731 - trivial stubs, kept inline
    _get_volume = lambda _kind: None  # noqa: E731
    _set_volume = lambda _kind, _percent: False  # noqa: E731
    _default_device_is_g8 = lambda _kind: False  # noqa: E731
    _watcher_class = None

#: ``available()`` shells out; the answer can't change during a run, so it is
#: computed once, lazily, on first use.
_available_cache: Optional[bool] = None


def available() -> bool:
    """Whether this platform's volume backend is usable (checked once)."""
    global _available_cache
    if _available_cache is None:
        _available_cache = bool(_available())
        if not _available_cache:
            _log(f"no usable volume backend on {PLATFORM}: sliders disabled")
    return _available_cache


def get_volume(kind: str) -> Optional[tuple[int, bool]]:
    """Volume of the default device as ``(percent 0-100, muted)``.

    Returns ``None`` if the value can't be read - no backend, no default
    device, or a device with no software volume control (a USB microphone on
    macOS, typically).
    """
    if not available():
        return None
    return _get_volume(kind)


def set_volume(kind: str, percent: int) -> bool:
    """Sets the default device's volume, clamped to 0-100. Never raises."""
    if not available():
        return False
    return bool(_set_volume(kind, max(0, min(100, int(percent)))))


def default_device_is_g8(kind: str) -> bool:
    """Whether the system's default output/input device is the Sound Blaster G8.

    Used by the GUI to know when a volume write would land on the card's own
    ALSA mixer, which must not happen while the card is still settling after a
    re-enumeration (see ``alsa_fix.SETTLE_DELAY_S``).
    """
    if not available():
        return False
    return bool(_default_device_is_g8(kind))


def start_watch(callback: Callable[[], None]) -> Optional[_Watcher]:
    """Starts watching for volume changes made outside the application.

    ``callback`` takes no argument and runs on a daemon thread: Tk callers must
    bounce back to the GUI thread themselves. Returns the handle to pass to
    :func:`stop_watch`, or ``None`` if watching isn't supported here.
    """
    if not available() or _watcher_class is None:
        return None
    watcher = _watcher_class(callback)
    watcher.start()
    return watcher


def stop_watch(watcher: Optional[_Watcher]) -> None:
    """Stops a watcher started by :func:`start_watch` (``None`` is a no-op)."""
    if watcher is not None:
        watcher.stop()
