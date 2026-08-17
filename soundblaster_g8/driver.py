"""
HID driver for the Creative Sound Blaster G8 sound card.

The protocol (framing, opcodes, parameter identifiers) is isolated in
:mod:`soundblaster_g8.protocol`, hidapi backend selection in
:mod:`soundblaster_g8.hidbackend`. This module only handles HID I/O.

Key implementation points (from Wireshark capture analysis):

1. The card exposes two HID interfaces. The control channel is the one
   with *usage page* ``0xFF01`` (interface 4). Opening the device via
   ``hid.device().open(VID, PID)`` can land on the Consumer interface
   (usage page 0x0C, interface 3), which rejects commands: so we
   explicitly open the correct ``path`` returned by ``enumerate()``.
2. Interface 4 has **no interrupt OUT endpoint**: every write is a
   ``SET_REPORT`` control transfer, ``wValue=0x0200`` / ``wLength=64``.
   We therefore always write ``b"\\x00" + pad_report(frame)``.
3. Responses arrive as 64-byte notifications on interrupt IN endpoint
   0x85, read via ``hid_read``.
4. Toggling Direct Mode (cmd 0x39) triggers a **USB reset** ~0.6 s after
   the ACK: the handle must be closed then reopened (:meth:`reconnect`).
5. hidapi handles aren't *thread-safe* and the GUI calls the driver from
   a worker thread: all I/O is serialized through a lock.

Compatible with macOS and Linux (and Windows via hidapi, untested).
"""

from __future__ import annotations

import platform
import threading
import time
from typing import Callable, Optional

from . import hidbackend, protocol
from .protocol import DecodedState, Frame

# Current platform: 'Darwin' (macOS), 'Linux', 'Windows'
PLATFORM = platform.system()

# USB identifiers
VENDOR_ID = 0x041E  # Creative Technology Ltd
PRODUCT_ID = 0x329B  # Sound Blaster G8

# Control HID interface (see protocol.py's docstring)
CONTROL_USAGE_PAGE = 0xFF01
CONTROL_INTERFACE_NUMBER = 4

# Input report size on the control interface
INPUT_REPORT_SIZE = protocol.REPORT_SIZE

# Default timeouts (ms)
ACK_TIMEOUT_MS = 300
DRAIN_TIMEOUT_MS = 5
PROBE_TIMEOUT_MS = 400

# Reconnection after the USB reset triggered by toggling Direct Mode.
# Capture timeline: reset at +0.6 s, device reappears at +1.3 s.
RECONNECT_TIMEOUT_S = 12.0
RECONNECT_INTERVAL_S = 0.25
RECONNECT_GRACE_S = 1.0

# Duration for which we absorb the 0x1a / 0x11 notifications emitted in a
# burst right after toggling Direct Mode.
TOGGLE_DRAIN_S = 0.25


class SoundBlasterG8Error(Exception):
    """Generic Sound Blaster G8 card error."""


class DeviceNotFoundError(SoundBlasterG8Error):
    """The control HID interface wasn't found."""


class DeviceConnectionError(SoundBlasterG8Error):
    """Opening the HID device failed (often a permissions issue)."""


class CommandRejectedError(SoundBlasterG8Error):
    """The card explicitly rejected the sent command."""


class FeatureNotSupportedError(SoundBlasterG8Error):
    """Feature not yet reverse-engineered: no known USB frame."""


def _log(message: str) -> None:
    print(f"[SoundBlasterG8Driver] {message}")


class SoundBlasterG8Driver:
    """HID driver for the Sound Blaster G8.

    The driver can run in simulation mode (no hardware detected): in that
    case commands are logged but nothing is sent, and :meth:`is_connected`
    returns ``False``.
    """

    def __init__(self, debug: bool = False, allow_simulation: bool = True):
        self._device = None
        self._device_info: dict = {}
        self._serial_number: Optional[str] = None
        self._debug = debug
        self._allow_simulation = allow_simulation
        self._simulated = False
        self._state = DecodedState()

        # hidapi handles aren't thread-safe: all I/O (write, read, open,
        # close) goes through this lock. RLock because set_direct_mode()
        # calls reconnect() while already holding the lock.
        self._io_lock = threading.RLock()
        self._in_reconnect = False

        #: Optional ``(bool) -> None`` callback called at the start and end
        #: of a reconnection, so the GUI can notify the user.
        self.on_reconnecting: Optional[Callable[[bool], None]] = None

        _log(f"Initializing the driver (platform: {PLATFORM}, "
             f"HID backend: {hidbackend.backend_name()})")

    # ------------------------------------------------------------------
    # Discovery and connection
    # ------------------------------------------------------------------

    @staticmethod
    def backend_name() -> str:
        """Name of the selected hidapi backend (``hidraw``, ``libusb``, ``iokit``...)."""
        return hidbackend.backend_name()

    @staticmethod
    def list_interfaces() -> list[dict]:
        """Returns every HID interface exposed by the card."""
        try:
            return hidbackend.enumerate(VENDOR_ID, PRODUCT_ID)
        except ImportError as exc:
            _log(f"HID backend unavailable: {exc}")
            return []
        except Exception as exc:  # pragma: no cover - depends on the backend
            _log(f"HID enumeration failed: {exc}")
            return []

    @classmethod
    def _select_control_interface(
        cls,
        interfaces: list[dict],
        serial_number: Optional[str] = None,
    ) -> Optional[dict]:
        """Picks the vendor interface (usage page 0xFF01 / interface 4).

        hidapi's enumeration order isn't guaranteed: so we filter
        explicitly instead of taking the first interface found. Three
        criteria, from most to least reliable:

        1. ``usage_page == 0xFF01``: normal path on macOS/IOKit and
           Linux/hidraw.
        2. ``interface_number == 4``: **normal path on Linux with the
           libusb backend**, which never populates ``usage_page`` (it's
           always 0 in ``hid_enumerate``). So this isn't a degraded case
           but the usual path for ``pip install hidapi`` wheels.
        3. ``input_report_length == 64``: last resort, since the Consumer
           interface uses 16-byte reports.
        """
        candidates = interfaces
        # Multiple cards plugged in: stick with the one already opened.
        if serial_number:
            same_card = [i for i in interfaces if i.get("serial_number") == serial_number]
            if same_card:
                candidates = same_card

        for info in candidates:
            if info.get("usage_page") == CONTROL_USAGE_PAGE:
                return info
        for info in candidates:
            if info.get("interface_number") == CONTROL_INTERFACE_NUMBER:
                return info
        for info in candidates:
            if info.get("input_report_length") == INPUT_REPORT_SIZE:
                return info
        return None

    def connect(self, force: bool = False) -> bool:
        """Opens the control HID interface.

        Args:
            force: reopens the device even if a handle is already cached.
                Used after a USB reset, where the old handle is still
                non-null but points to a dying node.

        Returns:
            ``True`` if the card is actually connected, ``False`` in
            simulation mode.

        Raises:
            DeviceNotFoundError / DeviceConnectionError if
            ``allow_simulation`` is ``False``.
        """
        with self._io_lock:
            if self._device is not None:
                if not force:
                    _log("Already connected")
                    return True
                self._close_quietly()

            _log("Attempting to connect to the Sound Blaster G8 card...")

            if not hidbackend.is_available():
                return self._fail(
                    "no hidapi backend available ('pip install hidapi')",
                    DeviceConnectionError,
                )

            interfaces = self.list_interfaces()
            _log(
                f"Looking for HID device VID={VENDOR_ID:04x}, PID={PRODUCT_ID:04x} "
                f"(backend {hidbackend.backend_name()})..."
            )

            if self._debug:
                for info in interfaces:
                    _log(
                        f"  interface={info.get('interface_number')} "
                        f"usage_page=0x{info.get('usage_page', 0):04x} "
                        f"usage=0x{info.get('usage', 0):04x} "
                        f"in_len={info.get('input_report_length')} "
                        f"path={info.get('path')}"
                    )

            if not interfaces:
                return self._fail(
                    "no HID interface found for the Sound Blaster G8",
                    DeviceNotFoundError,
                )

            target = self._select_control_interface(interfaces, self._serial_number)
            if target is None:
                return self._fail(
                    f"control interface (usage page 0x{CONTROL_USAGE_PAGE:04x} "
                    f"or interface {CONTROL_INTERFACE_NUMBER}) not found among "
                    f"{len(interfaces)} HID interface(s)",
                    DeviceNotFoundError,
                )

            try:
                device = hidbackend.open_path(target["path"])
            except Exception as exc:
                return self._fail(
                    f"unable to open the control interface: {exc}",
                    DeviceConnectionError,
                )

            self._device = device
            self._device_info = target
            self._simulated = False
            # Cached on first connect: after a USB reset the path changes,
            # but the serial number lets us reopen the same card.
            if not self._serial_number:
                self._serial_number = target.get("serial_number") or None

            try:
                device.set_nonblocking(False)
            except Exception:  # pragma: no cover - some backends ignore it
                pass

            _log(
                "HID connection established on the control interface "
                f"(interface={target.get('interface_number')}, "
                f"usage_page=0x{target.get('usage_page', 0):04x})"
            )
            if self._debug:
                _log(f"  Manufacturer: {target.get('manufacturer_string')}")
                _log(f"  Product     : {target.get('product_string')}")
                _log(f"  Serial      : {target.get('serial_number')}")

            # Any pending notifications provide the initial state.
            self.poll()
            return True

    def _fail(self, reason: str, exc_type: type[SoundBlasterG8Error]) -> bool:
        """Handles a connection failure: exception or fall back to simulation."""
        _log(f"ERROR: {reason}")
        if not self._allow_simulation:
            raise exc_type(reason)

        self._simulated = True
        _log("Simulation mode enabled (no command will be sent)")
        if PLATFORM == "Darwin":
            _log("On macOS, check: 'system_profiler SPUSBDataType | grep -A5 G8'")
        elif PLATFORM == "Linux":
            _log("On Linux, check 'lsusb', access to /dev/hidraw* and the udev rule")
            _log("  (see udev/99-soundblaster-g8.rules)")
        return False

    def _close_quietly(self) -> None:
        """Closes the current handle, ignoring any error (best effort)."""
        device, self._device = self._device, None
        if device is None:
            return
        try:
            device.close()
        except Exception as exc:
            if self._debug:
                _log(f"ignored error while closing handle: {exc}")

    def _invalidate_device(self, reason: str) -> None:
        """Marks the handle as dead (e.g. after a USB reset)."""
        _log(f"HID handle invalidated: {reason}")
        self._close_quietly()
        self._device_info = {}

    def disconnect(self) -> None:
        """Closes the HID connection."""
        with self._io_lock:
            if self._device is not None:
                self._close_quietly()
                _log("HID device closed")
            self._device_info = {}
            self._simulated = False

    def is_connected(self) -> bool:
        """``True`` only if real hardware is open."""
        return self._device is not None

    def is_simulated(self) -> bool:
        """``True`` if the driver is running without hardware."""
        return self._simulated

    def get_debug_info(self) -> dict:
        """Information useful for diagnostics."""
        return {
            "platform": PLATFORM,
            "hid_backend": hidbackend.backend_name(),
            "usage_page_available": hidbackend.provides_usage_page(),
            "vendor_id": f"{VENDOR_ID:04x}",
            "product_id": f"{PRODUCT_ID:04x}",
            "connected": self.is_connected(),
            "simulated": self._simulated,
            "interface_number": self._device_info.get("interface_number"),
            "usage_page": self._device_info.get("usage_page"),
            "product_string": self._device_info.get("product_string"),
            "serial_number": self._device_info.get("serial_number") or self._serial_number,
            "known_params": {
                f"0x{marker:02x}:0x{param:02x}": v
                for (marker, param), v in self._state.params.items()
            },
            "known_features": {
                f"0x{f:02x}/0x{p:04x}": v for (f, p), v in self._state.features.items()
            },
        }

    # ------------------------------------------------------------------
    # Reconnection after a USB reset
    # ------------------------------------------------------------------

    def reconnect(
        self,
        timeout_s: float = RECONNECT_TIMEOUT_S,
        interval_s: float = RECONNECT_INTERVAL_S,
    ) -> bool:
        """Reopens the control channel after a USB reset of the card.

        Timeline observed in the Wireshark capture, starting from the 0x39 command:
        reset/disconnect at +0.6 s, device reappears at +1.3 s. So we wait
        one grace second before starting to re-enumerate, then retry until
        the *deadline*: on Linux, ``udev`` may not yet have applied
        permissions on the new ``/dev/hidrawN`` (a classic race ->
        transient ``PermissionError``, worth retrying).

        Returns:
            ``True`` if a handle was reopened *and* validated by a probe
            (a real round-trip with the card).
        """
        with self._io_lock:
            if self._in_reconnect:
                return self._device is not None

            self._in_reconnect = True
            self._notify_reconnecting(True)
            try:
                # 1. the old handle is dead: close it without worrying
                #    about errors (the node may have disappeared already).
                self._close_quietly()
                self._device_info = {}

                # 2. grace delay: no point enumerating before the card has
                #    reappeared.
                time.sleep(RECONNECT_GRACE_S)

                deadline = time.monotonic() + timeout_s
                attempt = 0
                last_error = "no interface found"

                while time.monotonic() < deadline:
                    attempt += 1
                    try:
                        interfaces = hidbackend.enumerate(VENDOR_ID, PRODUCT_ID)
                        target = self._select_control_interface(
                            interfaces, self._serial_number
                        )
                        if target is None:
                            last_error = (
                                f"control interface missing "
                                f"({len(interfaces)} interface(s) enumerated)"
                            )
                            raise LookupError(last_error)

                        device = hidbackend.open_path(target["path"])
                    except (OSError, PermissionError, LookupError) as exc:
                        # Retryable: device hasn't reappeared yet, or udev
                        # hasn't finished applying permissions on the new node.
                        last_error = str(exc) or exc.__class__.__name__
                        if self._debug:
                            _log(f"reconnecting, attempt {attempt}: {last_error}")
                        time.sleep(interval_s)
                        continue
                    except Exception as exc:  # pragma: no cover - exotic backend
                        last_error = str(exc) or exc.__class__.__name__
                        if self._debug:
                            _log(f"reconnecting, attempt {attempt}: {last_error}")
                        time.sleep(interval_s)
                        continue

                    self._device = device
                    self._device_info = target
                    self._simulated = False
                    try:
                        device.set_nonblocking(False)
                    except Exception:  # pragma: no cover
                        pass

                    # 4. validate with a real round-trip: a handle opened on
                    #    a dying node sometimes accepts the open but nothing else.
                    if self._probe():
                        _log(
                            f"Reconnection succeeded after {attempt} attempt(s) "
                            f"(interface={target.get('interface_number')})"
                        )
                        self.poll()
                        return True

                    last_error = "the 0x09 probe did not respond"
                    self._close_quietly()
                    time.sleep(interval_s)

                _log(f"Reconnection FAILED after {timeout_s:.0f}s: {last_error}")
                return False
            finally:
                self._in_reconnect = False
                self._notify_reconnecting(False)

    def _notify_reconnecting(self, active: bool) -> None:
        callback = self.on_reconnecting
        if callback is None:
            return
        try:
            callback(active)
        except Exception as exc:  # pragma: no cover - depends on the caller
            _log(f"Error in the on_reconnecting callback: {exc}")

    def _probe(self) -> bool:
        """A real round-trip with the card: ``5a 09 01 02`` -> 0x09 response.

        The response contains the firmware version string
        (``1.2.250819.0903`` on the reference card, confirmed by the capture).
        Used to make sure we haven't reopened the dying node left by the
        USB reset: that one accepts the ``open`` but no longer responds.
        """
        try:
            frame = self._send_raw(
                protocol.build_info_probe(),
                expect="same_type",
                timeout_ms=PROBE_TIMEOUT_MS,
                allow_legacy_retry=False,
                recover=False,
            )
        except SoundBlasterG8Error as exc:
            if self._debug:
                _log(f"probe failed: {exc}")
            return False

        if frame is None:
            return False
        if self._debug:
            _log(f"probe OK, firmware={frame.info_text!r}")
        return True

    # ------------------------------------------------------------------
    # Transport layer
    # ------------------------------------------------------------------

    def _read_frame(self, timeout_ms: int, recover: bool = True) -> Optional[Frame]:
        """Reads a notification and decodes it (``None`` if nothing arrives)."""
        with self._io_lock:
            device = self._device
            if device is None:
                return None
            try:
                data = device.read(INPUT_REPORT_SIZE, timeout_ms)
            except OSError as exc:
                # Dead handle (USB reset, cable unplugged): discard it and
                # attempt a reconnection.
                self._invalidate_device(f"HID read failed: {exc}")
                if recover:
                    self.reconnect()
                return None
            except Exception as exc:
                _log(f"HID read error: {exc}")
                return None

        if not data:
            return None

        frame = protocol.parse_frame(bytes(data))
        if frame is None:
            if self._debug:
                _log(f"<- undecodable report: {bytes(data).hex()}")
            return None

        self._state.apply(frame)
        if self._debug:
            _log(f"<- {frame.describe()}")
        return frame

    def poll(
        self,
        timeout_ms: int = DRAIN_TIMEOUT_MS,
        max_frames: int = 16,
        recover: bool = False,
    ) -> list[Frame]:
        """Drains the notification queue and updates the state cache.

        Args:
            recover: attempt a reconnection if the handle turns out to be
                dead. False by default: after toggling Direct Mode, the
                device disappearing is expected and handled by the caller.
        """
        frames: list[Frame] = []
        for _ in range(max_frames):
            frame = self._read_frame(timeout_ms, recover=recover)
            if frame is None:
                break
            frames.append(frame)
        return frames

    def send_frame(
        self,
        frame_type: int,
        payload: bytes,
        expect_ack: bool = True,
        timeout_ms: int = ACK_TIMEOUT_MS,
    ) -> Optional[Frame]:
        """Sends a frame and returns the matching ACK.

        Args:
            frame_type: frame type (e.g. ``protocol.CMD_SET``).
            payload: frame content, header excluded.
            expect_ack: wait for and return the acknowledgment.
            timeout_ms: ACK wait budget.

        Raises:
            CommandRejectedError: the card responded with the error bit or
                a non-zero status.
        """
        data = protocol.build_frame(frame_type, payload)
        return self._send_raw(
            data,
            expect="ack" if expect_ack else None,
            timeout_ms=timeout_ms,
        )

    def _write(self, buf: bytes, recover: bool = True) -> bool:
        """Raw HID write, locked, with dead-handle detection."""
        with self._io_lock:
            device = self._device
            if device is None:
                return False
            _log(f"-> {buf.hex()} ({len(buf)} bytes)")
            try:
                written = device.write(buf)
            except OSError as exc:
                self._invalidate_device(f"HID write failed: {exc}")
                if recover:
                    self.reconnect()
                return False
            except Exception as exc:
                raise DeviceConnectionError(f"HID write failed: {exc}") from exc

        if written != len(buf) and self._debug:
            _log(f"WARNING: {written} byte(s) written out of {len(buf)}")
        return True

    def _wait_for(
        self,
        expect: str,
        frame_type: int,
        timeout_ms: int,
        recover: bool,
    ) -> Optional[Frame]:
        """Waits for the expected response, ignoring unrelated notifications.

        ``expect="ack"``       : type-0x02 frame whose ``ack_command`` is
        ``frame_type`` (writes).
        ``expect="same_type"`` : frame of the same type as the request
        (reads: 0x39 -> 0x39, 0x09 -> 0x09, 0x11 -> 0x11).
        """
        deadline = time.monotonic() + timeout_ms / 1000.0
        while True:
            remaining_ms = int((deadline - time.monotonic()) * 1000)
            if remaining_ms <= 0:
                return None

            frame = self._read_frame(min(remaining_ms, 50), recover=recover)
            if frame is None:
                if self._device is None:
                    return None
                continue

            if frame.is_error and frame.base_type in (protocol.NOTIF_ACK, frame_type):
                raise CommandRejectedError(
                    f"command rejected by the card: {frame.describe()}"
                )

            if expect == "ack":
                if frame.is_ack and frame.ack_command == frame_type:
                    if not frame.ack_ok:
                        raise CommandRejectedError(
                            f"error status {frame.ack_status}: {frame.describe()}"
                        )
                    return frame
            elif expect == "same_type":
                if frame.base_type == frame_type:
                    return frame

    def _send_raw(
        self,
        frame: bytes,
        expect: Optional[str] = "ack",
        timeout_ms: int = ACK_TIMEOUT_MS,
        allow_legacy_retry: bool = True,
        recover: bool = True,
    ) -> Optional[Frame]:
        """Sends a frame and optionally waits for the matching response.

        Single transport (see ``protocol``): ``b"\\x00" + pad_report(frame)``,
        i.e. ``SET_REPORT wValue=0x0200 wLength=64``. The first byte is
        consumed by hidapi as the report ID.

        Args:
            frame: unpadded ``5a <type> <len> <payload>`` frame.
            expect: ``"ack"`` (type-0x02 response), ``"same_type"``
                (response of the same type as the request), or ``None``
                (fire-and-forget).
            allow_legacy_retry: on timeout, retry **exactly once** with the
                old form (bare 8-byte frame, report ID 0x5A,
                ``wValue=0x025A``). Safety net in case the card turns out
                to be stricter about Scout Mode than what the capture shows.
        """
        if not frame or frame[0] != protocol.MAGIC:
            raise ValueError(f"invalid frame (expected magic 0x5a): {bytes(frame).hex()}")
        frame_type = frame[1]

        with self._io_lock:
            if self._device is None:
                _log(f"[simulation] -> {bytes(frame).hex()}")
                return None

            # Purge: pending notifications would throw off the matching.
            # If the handle is dead (unannounced USB reset), the purge
            # triggers a reconnection and the write goes out on the new handle.
            self.poll(recover=recover)
            if self._device is None:
                _log("Cannot send: no valid HID handle left")
                return None

            report = bytes([protocol.REPORT_ID]) + protocol.pad_report(frame)
            if not self._write(report, recover=recover):
                return None

            if expect is None:
                return None

            response = self._wait_for(expect, frame_type, timeout_ms, recover)
            if response is not None:
                return response

            if not allow_legacy_retry:
                _log("No response received (timeout)")
                return None

            # Legacy fallback: bare frame, hidapi takes 0x5A as the report ID
            # -> wValue=0x025A. A single attempt, explicitly logged.
            _log(
                "No response to the 64 B padded form (wValue=0x0200): "
                "a single retry with the old form "
                f"({len(frame)} B, report ID 0x{protocol.LEGACY_REPORT_ID:02x}, "
                "wValue=0x025a)"
            )
            if not self._write(bytes(frame), recover=recover):
                return None

            response = self._wait_for(expect, frame_type, timeout_ms, recover)
            if response is None:
                _log("No response received (timeout, even after the retry)")
            else:
                _log(
                    "WARNING: the card only accepts the old form "
                    "(report ID 0x5a) - please report this, the unified "
                    "transport is supposed to work per the USB capture"
                )
            return response

    # ------------------------------------------------------------------
    # Generic functions
    # ------------------------------------------------------------------

    def set_feature_u16(self, feature: int, param: int, value: int) -> bool:
        """Writes a 16-bit parameter and checks the ACK's echo."""
        if self._device is None:
            _log(
                f"[simulation] feature=0x{feature:02x} param=0x{param:04x} value={value}"
            )
            return False

        payload = (
            bytes([feature])
            + param.to_bytes(2, "little")
            + value.to_bytes(2, "little")
        )
        ack = self.send_frame(protocol.CMD_SET, payload)
        if ack is None:
            return False

        if ack.ack_feature != feature or ack.ack_param != param:
            _log(
                "WARNING: the ACK doesn't match the command "
                f"(expected 0x{feature:02x}/0x{param:04x}, "
                f"got {ack.describe()})"
            )
            return False

        if ack.ack_value is not None and ack.ack_value != value:
            _log(
                f"WARNING: applied value {ack.ack_value} "
                f"instead of {value}"
            )
            return False

        return True

    def set_feature_bool(self, feature: int, param: int, enabled: bool) -> bool:
        return self.set_feature_u16(feature, param, 1 if enabled else 0)

    def get_feature_cached(self, feature: int, param: int) -> Optional[int]:
        """Last known value of a parameter (from received ACKs)."""
        self.poll()
        return self._state.features.get((feature, param))

    # ------------------------------------------------------------------
    # Scout Mode (confirmed by the USB capture)
    # ------------------------------------------------------------------

    def set_scout_mode(self, enabled: bool) -> bool:
        """Enables/disables Scout Mode.

        Frame sent: ``5a 26 05 07 02 00 01 00`` (ON) /
        ``5a 26 05 07 02 00 00 00`` (OFF), zero-padded to 64 bytes.

        Returns:
            ``True`` if the card acknowledged the command.
        """
        action = "enabling" if enabled else "disabling"
        _log(f"Scout Mode: {action}")
        with self._io_lock:
            try:
                ok = self.set_feature_bool(*protocol.SCOUT_MODE, enabled)
            except SoundBlasterG8Error as exc:
                _log(f"Scout Mode ERROR: {exc}")
                return False

        if ok:
            _log(f"Scout Mode {'enabled' if enabled else 'disabled'} (confirmed by the card)")
        elif self._device is not None:
            _log("Scout Mode: the card did not confirm the command")
        return ok

    def get_scout_mode(self) -> Optional[bool]:
        """Scout Mode state based on the last ACK received.

        The read command hasn't been identified yet: we rely
        on the echo of commands already sent. Returns ``None`` if the
        state is unknown.
        """
        value = self.get_feature_cached(*protocol.SCOUT_MODE)
        return None if value is None else bool(value)

    # ------------------------------------------------------------------
    # Direct Mode (confirmed by the USB capture)
    # ------------------------------------------------------------------

    def set_direct_mode(self, enabled: bool) -> bool:
        """Enables/disables Direct Mode.

        Full sequence (see the timeline in ``protocol``):

        1. purge pending notifications;
        2. send ``5a 39 03 00 05 <0|1>`` padded to 64 bytes;
        3. wait for the ACK ``5a 02 0a 39 00 05 <0|1>`` (arrives in ~0.2 ms,
           300 ms budget) with param/value echo verification;
        4. drain the 0x1a notifications and 0x11 dumps that follow;
        5. the card re-enumerates (USB reset at +0.6 s): :meth:`reconnect`.

        Returns:
            ``True`` only if the ACK is correct **and** the reconnection is
            validated by a probe.
        """
        action = "enabling" if enabled else "disabling"
        _log(f"Direct Mode: {action}")

        with self._io_lock:
            if self._device is None:
                _log(f"[simulation] -> {protocol.build_direct_mode(enabled).hex()}")
                return False

            try:
                ack = self._send_raw(
                    protocol.build_direct_mode(enabled),
                    expect="ack",
                    timeout_ms=ACK_TIMEOUT_MS,
                )
            except SoundBlasterG8Error as exc:
                _log(f"Direct Mode ERROR: {exc}")
                return False

            if ack is None:
                _log("Direct Mode: no ACK for the 0x39 command (timeout)")
                return False

            # The 0x39 ACK doesn't have the same layout as the 0x26 one.
            expected = 1 if enabled else 0
            if ack.dm_ack_param != protocol.PARAM_DIRECT_MODE:
                _log(
                    "WARNING: the 0x39 ACK doesn't reference param "
                    f"0x{protocol.PARAM_DIRECT_MODE:02x} ({ack.describe()})"
                )
                return False
            if ack.dm_ack_value != expected:
                _log(
                    f"WARNING: applied value {ack.dm_ack_value} "
                    f"instead of {expected} ({ack.describe()})"
                )
                return False

            _log("Direct Mode: command acknowledged, draining notifications...")
            self._drain_toggle_notifications()

            _log("Direct Mode: the card is re-enumerating, reconnecting...")
            if not self.reconnect():
                _log(
                    "Direct Mode: command accepted but the card could not "
                    "be reopened after the USB reset"
                )
                return False

            _log(f"Direct Mode {'enabled' if enabled else 'disabled'} (confirmed)")
            return True

    def _drain_toggle_notifications(self) -> None:
        """Absorbs the 0x1a / 0x11 frames emitted in a burst after a 0x39 toggle."""
        deadline = time.monotonic() + TOGGLE_DRAIN_S
        while time.monotonic() < deadline:
            frames = self.poll(timeout_ms=20, max_frames=8)
            if not frames:
                break

    def get_direct_mode(self) -> Optional[bool]:
        """Queries the card for Direct Mode's state.

        Request ``5a 39 05 01 20 00 00 00`` -> type-0x39 response
        ``5a 39 05 01 <bits> 40 00 00``; bit 0x20 of the 2nd payload byte
        indicates Direct Mode is active.

        Returns:
            ``None`` if the card isn't connected or doesn't respond.
        """
        with self._io_lock:
            if self._device is None:
                return None
            try:
                frame = self._send_raw(
                    protocol.build_direct_mode_status(),
                    expect="same_type",
                    timeout_ms=ACK_TIMEOUT_MS,
                )
            except SoundBlasterG8Error as exc:
                _log(f"Unable to read Direct Mode: {exc}")
                return None

        if frame is None:
            _log("Direct Mode read: no response")
            return None
        return frame.direct_mode_enabled

    # ------------------------------------------------------------------
    # Sound mode / equalizer (confirmed by the "Sound Mode" captures)
    # ------------------------------------------------------------------

    def _set_float_param(self, marker: int, param: int, value: float, tag: str) -> bool:
        """Sends a single CMD_SET_FLOAT write and checks the ACK.

        Shared body of the three float namespaces (sound mode/EQ, CrystalVoice
        and decoder): they differ only by the TLV marker and by the ``tag``
        prefixing their log lines.
        """
        if self._device is None:
            _log(f"[simulation] {tag}SET_FLOAT param=0x{param:02x} value={value}")
            return False

        try:
            # build_set_float() returns an already-complete frame (like
            # build_direct_mode()): go through _send_raw directly, not
            # send_frame() which would re-wrap the payload in a frame.
            ack = self._send_raw(
                protocol.build_set_float(param, value, marker=marker), expect="ack"
            )
        except SoundBlasterG8Error as exc:
            _log(f"{tag}SET_FLOAT ERROR param=0x{param:02x}: {exc}")
            return False

        if ack is None or ack.ack_command != protocol.CMD_SET_FLOAT or not ack.ack_ok:
            _log(
                f"WARNING: no valid ACK for {tag}param=0x{param:02x} "
                f"({ack.describe() if ack else 'timeout'})"
            )
            return False
        return True

    def set_sound_mode_param(self, param: int, value: float) -> bool:
        """Sends a single CMD_SET_FLOAT write and checks the ACK."""
        return self._set_float_param(protocol.TLV_FLOAT, param, value, "")

    def set_sound_mode(self, writes: list[tuple[int, float]]) -> bool:
        """Replays a sequence of CMD_SET_FLOAT writes (a sound mode).

        The sequence order is that of the original USB capture (see
        :mod:`soundblaster_g8.sound_modes`): it must be preserved as-is.
        Unlike Direct Mode, these writes don't trigger a USB reset of the
        card.

        Returns:
            ``True`` only if **all** writes were acknowledged.
        """
        _log(f"Sound mode: sending {len(writes)} parameter(s)")
        with self._io_lock:
            all_ok = True
            for param, value in writes:
                if not self.set_sound_mode_param(param, value):
                    all_ok = False
            _log(f"Sound mode {'applied' if all_ok else 'partially applied'}")
            return all_ok

    def eq_set_band(self, index: int, value: float) -> bool:
        """Writes a single EQ band (same mechanism as :meth:`set_sound_mode`).

        A band is just one more `CMD_SET_FLOAT` parameter: the param id is
        `protocol.EQ_BAND_PARAMS[index]` (0x0b..0x14).
        """
        if not 0 <= index < len(protocol.EQ_BAND_PARAMS):
            raise ValueError(f"band index out of range: {index}")
        return self.set_sound_mode_param(protocol.EQ_BAND_PARAMS[index], value)

    def eq_get_all_bands(self) -> Optional[list[float]]:
        """Last known values of the 10 bands (from the notification cache).

        As with :meth:`get_feature_cached`, the card has no dedicated read
        command: we rely on the ``PARAMS`` dumps received after a write.
        Returns ``None`` as long as a band has never been observed.
        """
        self.poll()
        bands: list[float] = []
        for param in protocol.EQ_BAND_PARAMS:
            value = self._state.params.get((protocol.TLV_FLOAT, param))
            if value is None:
                return None
            bands.append(value)
        return bands

    def eq_set_preamp(self, value: float) -> bool:
        """Writes the Preamp (param 0x0a), same mechanism as :meth:`eq_set_band`."""
        return self.set_sound_mode_param(protocol.PARAM_PREAMP, value)

    def eq_get_preamp(self) -> Optional[float]:
        """Last known Preamp value (same limitation as :meth:`eq_get_all_bands`)."""
        self.poll()
        return self._state.params.get((protocol.TLV_FLOAT, protocol.PARAM_PREAMP))

    # ------------------------------------------------------------------
    # CrystalVoice (confirmed by Wireshark captures)
    # ------------------------------------------------------------------

    def set_crystalvoice_param(self, param: int, value: float) -> bool:
        """Sends a single CrystalVoice CMD_SET_FLOAT write and checks the ACK.

        Same mechanism as :meth:`set_sound_mode_param`, but with the
        TLV_CRYSTALVOICE marker (0x95) instead of TLV_FLOAT (0x96).
        """
        return self._set_float_param(protocol.TLV_CRYSTALVOICE, param, value, "CV ")

    def get_crystalvoice_param(self, param: int) -> Optional[float]:
        """Last known value of a CrystalVoice parameter (from the notification cache)."""
        self.poll()
        return self._state.params.get((protocol.TLV_CRYSTALVOICE, param))

    def set_crystalvoice_noise_reduction(self, enabled: bool) -> bool:
        return self.set_crystalvoice_param(
            protocol.PARAM_CV_NOISE_REDUCTION_ENABLED, 1.0 if enabled else 0.0
        )

    def get_crystalvoice_noise_reduction(self) -> Optional[bool]:
        value = self.get_crystalvoice_param(protocol.PARAM_CV_NOISE_REDUCTION_ENABLED)
        return None if value is None else bool(value)

    def set_crystalvoice_noise_reduction_level(self, value: float) -> bool:
        return self.set_crystalvoice_param(protocol.PARAM_CV_NOISE_REDUCTION_LEVEL, value)

    def get_crystalvoice_noise_reduction_level(self) -> Optional[float]:
        return self.get_crystalvoice_param(protocol.PARAM_CV_NOISE_REDUCTION_LEVEL)

    def set_crystalvoice_echo_cancellation(self, enabled: bool) -> bool:
        return self.set_crystalvoice_param(
            protocol.PARAM_CV_ECHO_CANCELLATION, 1.0 if enabled else 0.0
        )

    def get_crystalvoice_echo_cancellation(self) -> Optional[bool]:
        value = self.get_crystalvoice_param(protocol.PARAM_CV_ECHO_CANCELLATION)
        return None if value is None else bool(value)

    def set_crystalvoice_smart_volume(self, enabled: bool) -> bool:
        return self.set_crystalvoice_param(protocol.PARAM_CV_SMART_VOICE, 1.0 if enabled else 0.0)

    def get_crystalvoice_smart_volume(self) -> Optional[bool]:
        value = self.get_crystalvoice_param(protocol.PARAM_CV_SMART_VOICE)
        return None if value is None else bool(value)

    def set_crystalvoice_params(self, writes: list[tuple[int, float]]) -> bool:
        """Replays a sequence of CrystalVoice writes (a Voice Morph / mic-EQ preset).

        CrystalVoice counterpart of :meth:`set_sound_mode`: same "replay the
        capture in order" contract, only the TLV marker differs. The enable
        bit isn't part of the sequence (see
        :mod:`soundblaster_g8.crystalvoice_presets`).

        Returns:
            ``True`` only if **all** writes were acknowledged.
        """
        _log(f"CrystalVoice preset: sending {len(writes)} parameter(s)")
        with self._io_lock:
            all_ok = True
            for param, value in writes:
                if not self.set_crystalvoice_param(param, value):
                    all_ok = False
            _log(f"CrystalVoice preset {'applied' if all_ok else 'partially applied'}")
            return all_ok

    def set_crystalvoice_voice_morph(self, enabled: bool) -> bool:
        return self.set_crystalvoice_param(
            protocol.PARAM_CV_VOICE_MORPH_ENABLED, 1.0 if enabled else 0.0
        )

    def get_crystalvoice_voice_morph(self) -> Optional[bool]:
        value = self.get_crystalvoice_param(protocol.PARAM_CV_VOICE_MORPH_ENABLED)
        return None if value is None else bool(value)

    def set_crystalvoice_mic_equalizer(self, enabled: bool) -> bool:
        return self.set_crystalvoice_param(
            protocol.PARAM_CV_MIC_EQ_ENABLED, 1.0 if enabled else 0.0
        )

    def get_crystalvoice_mic_equalizer(self) -> Optional[bool]:
        value = self.get_crystalvoice_param(protocol.PARAM_CV_MIC_EQ_ENABLED)
        return None if value is None else bool(value)

    # ------------------------------------------------------------------
    # Decoder (confirmed by a Wireshark capture)
    # ------------------------------------------------------------------

    def set_decoder_mode(self, value: float) -> bool:
        """Writes the decoder's Dynamic Range Control mode (marker 0x97).

        ``value`` is the raw float read from the capture (see
        ``controller.DECODER_MODES``), not an index.
        """
        return self._set_float_param(
            protocol.TLV_DECODER, protocol.PARAM_DECODER_MODE, value, "decoder "
        )

    def get_decoder_mode_value(self) -> Optional[float]:
        """Last known decoder mode value (same limitation as :meth:`get_crystalvoice_param`)."""
        self.poll()
        return self._state.params.get((protocol.TLV_DECODER, protocol.PARAM_DECODER_MODE))

    # ------------------------------------------------------------------
    # Not yet reverse-engineered functions
    # ------------------------------------------------------------------

    def _unsupported(self, name: str) -> bool:
        _log(
            f"'{name}' is not implemented yet: the corresponding USB frame "
            "hasn't been captured. Use 'python tools/g8_probe.py --monitor' "
            "while the Creative application changes this setting."
        )
        return False

    def eq_load_preset(self, preset_name: str) -> bool:
        return self._unsupported(f"EQ preset '{preset_name}'")

    def eq_save_preset(self, preset_name: str) -> bool:
        return self._unsupported(f"Saving EQ preset '{preset_name}'")

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "SoundBlasterG8Driver":
        self.connect()
        return self

    def __exit__(self, *_exc) -> None:
        self.disconnect()


# Singleton instance
_driver_instance: Optional[SoundBlasterG8Driver] = None


def get_driver(debug: bool = False) -> SoundBlasterG8Driver:
    """Returns the driver's singleton instance."""
    global _driver_instance
    if _driver_instance is None:
        _driver_instance = SoundBlasterG8Driver(debug=debug)
    return _driver_instance
