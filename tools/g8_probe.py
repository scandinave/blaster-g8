#!/usr/bin/env python3
"""
Diagnostic and reverse-engineering tool for the Sound Blaster G8.

Examples
--------
Show the selected hidapi backend (hidraw / libusb / iokit)::

    python tools/g8_probe.py --backend

List the HID interfaces and their descriptors::

    python tools/g8_probe.py --list

Enable / disable Scout Mode (end-to-end test, no GUI)::

    python tools/g8_probe.py --scout on
    python tools/g8_probe.py --scout off

Enable / disable Direct Mode, then re-read the hardware state::

    python tools/g8_probe.py --direct on --debug
    python tools/g8_probe.py --direct-status
    python tools/g8_probe.py --direct off --debug

Chain N Direct Mode toggles in a single process (validates the
reconnection after the USB reset)::

    python tools/g8_probe.py --reconnect-test 5

Listen to the card's notifications (useful while operating the official
Creative application, to discover new parameters)::

    python tools/g8_probe.py --monitor

Send an arbitrary frame (type + payload in hex)::

    python tools/g8_probe.py --raw 26 0702000100

Sweep a parameter's values to identify a feature::

    python tools/g8_probe.py --set 07:0002=1

List then apply a sound mode (equalizer + acoustic engine)::

    python tools/g8_probe.py --list-sound-modes
    python tools/g8_probe.py --sound-mode esport --debug
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Allows direct execution from the repo without prior installation.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from soundblaster_g8 import hidbackend, protocol  # noqa: E402
from soundblaster_g8.driver import (  # noqa: E402
    SoundBlasterG8Driver,
    SoundBlasterG8Error,
)
from soundblaster_g8.sound_modes import SOUND_MODES  # noqa: E402


def _truthy(value: str) -> bool:
    return value.lower() in ("on", "1", "true", "yes")


def cmd_backend() -> int:
    """Shows the selected hidapi backend and the available modules."""
    print(f"Platform          : {sys.platform}")
    try:
        info = hidbackend.get_backend()
    except ImportError as exc:
        print(f"HID backend       : NONE ({exc})")
        return 1

    print(f"Selected backend  : {info.name}")
    print(f"Module            : {info.module.__name__}")
    print(f"usage_page listed : {'yes' if info.provides_usage_page else 'no'}")

    if sys.platform.startswith("linux"):
        for name in ("hidraw", "hid"):
            try:
                __import__(name)
                state = "available"
            except ImportError:
                state = "absent"
            print(f"  module {name:<7}: {state}")
        if info.name == "libusb":
            print()
            print("Note: with libusb, usage_page is always 0 in")
            print("hid_enumerate; control-interface selection falls back")
            print("to interface_number == 4. To force hidraw:")
            print("  HIDAPI_WITH_HIDRAW=1 pip install --no-binary :all: hidapi")
    return 0


def cmd_list() -> int:
    """Shows the HID interfaces exposed by the card."""
    interfaces = SoundBlasterG8Driver.list_interfaces()
    if not interfaces:
        print("No HID interface found (card unplugged or insufficient permissions).")
        return 1

    print(f"Backend: {SoundBlasterG8Driver.backend_name()}")
    print(f"{len(interfaces)} HID interface(s) found:\n")
    selected = SoundBlasterG8Driver._select_control_interface(interfaces)
    for info in interfaces:
        usage_page = info.get("usage_page", 0)
        marker = "  <== control channel" if info is selected else ""
        print(f"- interface_number : {info.get('interface_number')}{marker}")
        print(f"  usage_page       : 0x{usage_page:04x}")
        print(f"  usage            : 0x{info.get('usage', 0):04x}")
        print(f"  input_report_len : {info.get('input_report_length')}")
        print(f"  product          : {info.get('product_string')}")
        print(f"  serial           : {info.get('serial_number')}")
        print(f"  path             : {info.get('path')}")
        print()
    return 0


def cmd_scout(driver: SoundBlasterG8Driver, value: str) -> int:
    enabled = _truthy(value)
    ok = driver.set_scout_mode(enabled)
    print()
    print(f"Result: {'SUCCESS' if ok else 'FAILURE'}")
    print(f"Known Scout Mode state: {driver.get_scout_mode()}")
    return 0 if ok else 1


def cmd_direct(driver: SoundBlasterG8Driver, value: str) -> int:
    enabled = _truthy(value)
    ok = driver.set_direct_mode(enabled)
    print()
    print(f"Result: {'SUCCESS' if ok else 'FAILURE'}")
    print(f"State re-read from the card: {driver.get_direct_mode()}")
    return 0 if ok else 1


def cmd_direct_status(driver: SoundBlasterG8Driver) -> int:
    """Queries the card for Direct Mode's state (0x39 request)."""
    state = driver.get_direct_mode()
    if state is None:
        print("Direct Mode: undetermined state (no response from the card)")
        return 1
    print(f"Direct Mode: {'ENABLED' if state else 'disabled'}")
    return 0


def cmd_reconnect_test(driver: SoundBlasterG8Driver, count: int) -> int:
    """Chains N Direct Mode toggles in a single process.

    Each toggle triggers a USB reset: this test validates that the driver
    finds the card again and stays usable, even after several cycles.
    """
    initial = driver.get_direct_mode()
    print(f"Initial Direct Mode state: {initial}")
    target = bool(initial) if initial is not None else False

    failures = 0
    for i in range(1, count + 1):
        target = not target
        print(f"\n=== Toggle {i}/{count}: Direct Mode -> {'ON' if target else 'OFF'} ===")
        started = time.monotonic()
        ok = driver.set_direct_mode(target)
        elapsed = time.monotonic() - started
        state = driver.get_direct_mode()
        coherent = state is None or state == target
        print(
            f"  result={'SUCCESS' if ok else 'FAILURE'} "
            f"state re-read={state} ({'consistent' if coherent else 'INCONSISTENT'}) "
            f"duration={elapsed:.2f}s"
        )
        if not ok or not coherent:
            failures += 1

    print(f"\n{count - failures}/{count} toggle(s) succeeded.")
    if initial is not None and bool(initial) != target:
        print("Restoring the initial state...")
        driver.set_direct_mode(bool(initial))
    return 0 if failures == 0 else 1


def cmd_list_sound_modes() -> int:
    """Shows the available sound modes (generated from the captures)."""
    print(f"{len(SOUND_MODES)} sound mode(s) available:\n")
    for slug, mode in SOUND_MODES.items():
        print(f"  {slug:<28} {mode.label}")
    return 0


def cmd_sound_mode(driver: SoundBlasterG8Driver, slug: str) -> int:
    mode = SOUND_MODES.get(slug)
    if mode is None:
        print(f"Unknown sound mode: {slug!r}")
        print("Use --list-sound-modes to see the available slugs.")
        return 2

    print(f"Applying mode \"{mode.label}\" ({len(mode.writes)} parameter(s))...")
    ok = driver.set_sound_mode(list(mode.writes))
    print()
    print(f"Result: {'SUCCESS' if ok else 'FAILURE'}")
    print(f"Applied EQ bands: {mode.bands}")
    return 0 if ok else 1


def cmd_set(driver: SoundBlasterG8Driver, spec: str) -> int:
    """``--set feature:param=value`` (values in hex or decimal)."""
    try:
        target, raw_value = spec.split("=", 1)
        feature_str, param_str = target.split(":", 1)
        feature = int(feature_str, 0) if feature_str.startswith("0x") else int(feature_str, 16)
        param = int(param_str, 0) if param_str.startswith("0x") else int(param_str, 16)
        value = int(raw_value, 0)
    except ValueError:
        print("Expected format: --set 07:0002=1 (feature:param in hex, decimal value)")
        return 2

    ok = driver.set_feature_u16(feature, param, value)
    print(f"Result: {'SUCCESS' if ok else 'FAILURE'}")
    return 0 if ok else 1


def cmd_raw(driver: SoundBlasterG8Driver, frame_type: str, payload_hex: str) -> int:
    try:
        ftype = int(frame_type, 16)
        payload = bytes.fromhex(payload_hex)
    except ValueError:
        print("Expected format: --raw 26 0702000100")
        return 2

    try:
        ack = driver.send_frame(ftype, payload)
    except SoundBlasterG8Error as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"ACK: {ack.describe() if ack else 'none'}")
    return 0


def cmd_monitor(driver: SoundBlasterG8Driver, duration: float) -> int:
    """Listens for the card's spontaneous notifications."""
    print(
        f"Listening for notifications for {duration:.0f}s "
        "(Ctrl+C to stop). Operate the Creative application now.\n"
    )
    deadline = time.monotonic() + duration
    count = 0
    try:
        while time.monotonic() < deadline:
            for frame in driver.poll(timeout_ms=200, max_frames=32):
                count += 1
                stamp = time.strftime("%H:%M:%S")
                print(f"[{stamp}] {frame.describe()}")
                print(f"          raw={frame.raw.hex()}")
    except KeyboardInterrupt:
        print("\nInterrupted.")

    print(f"\n{count} notification(s) received.")
    print("Known parameters:", driver.get_debug_info()["known_params"])
    return 0


def _check(label: str, got, expected) -> bool:
    ok = got == expected
    print(f"{label:<28}: {got} (expected {expected}) {'OK' if ok else 'FAIL'}")
    return ok


def cmd_selftest() -> int:
    """Checks frame encoding against the bytes actually captured."""
    ok = True

    # --- Encoding (vectors from the USB captures) ---
    ok &= _check("Scout ON", protocol.build_scout_mode(True).hex(), "5a26050702000100")
    ok &= _check("Scout OFF", protocol.build_scout_mode(False).hex(), "5a26050702000000")
    ok &= _check("Direct ON", protocol.build_direct_mode(True).hex(), "5a3903000501")
    ok &= _check("Direct OFF", protocol.build_direct_mode(False).hex(), "5a3903000500")
    ok &= _check("Direct status (req)",
                 protocol.build_direct_mode_status().hex(), "5a39050120000000")
    ok &= _check("Info probe", protocol.build_info_probe().hex(), "5a090102")
    ok &= _check(
        "SET_FLOAT (EQ on)",
        protocol.build_set_float(protocol.PARAM_EQ_ENABLED, 1.0).hex(),
        "5a12070196090000803f",
    )
    ok &= _check(
        "SET_FLOAT (CrystalVoice Noise Reduction ON)",
        protocol.build_set_crystalvoice_float(
            protocol.PARAM_CV_NOISE_REDUCTION_ENABLED, 1.0
        ).hex(),
        "5a12070195040000803f",
    )
    ok &= _check(
        "SET_FLOAT (CrystalVoice Smart Volume OFF)",
        protocol.build_set_crystalvoice_float(protocol.PARAM_CV_SMART_VOICE, 0.0).hex(),
        "5a120701952c00000000",
    )
    # The three decoder modes, byte for byte from Decodeur.pcapng.
    for mode_name, mode_value, expected in (
        ("Normal", 1.0, "5a12070197020000803f"),
        ("Full", 3.0, "5a120701970200004040"),
        ("Night", 2.0, "5a120701970200000040"),
    ):
        ok &= _check(
            f"SET_FLOAT (Decoder {mode_name})",
            protocol.build_set_decoder_float(protocol.PARAM_DECODER_MODE, mode_value).hex(),
            expected,
        )
    ok &= _check(
        "Generated sound modes",
        len(SOUND_MODES) > 0,
        True,
    )

    # Direct Mode OFF frame as it goes out on the wire: 64 padded bytes,
    # preceded by report ID 0x00 (wValue=0x0200, wLength=64).
    padded = protocol.pad_report(protocol.build_direct_mode(False))
    ok &= _check("Report padding", len(padded), protocol.REPORT_SIZE)
    ok &= _check("Direct OFF padded", padded.hex(), "5a3903000500" + "00" * 58)

    print()

    # --- Decoding actually-observed frames ---
    ack_dm = protocol.parse_frame(bytes.fromhex("5a020a390005000000000000" + "00" * 52))
    if ack_dm is None:
        print("ACK 0x39                    : decoding FAILED")
        ok = False
    else:
        print(f"Decoded ACK 0x39             : {ack_dm.describe()}")
        ok &= _check("  ACK 0x39 cmd", ack_dm.ack_command, protocol.CMD_DIRECT_MODE)
        ok &= _check("  ACK 0x39 status", ack_dm.ack_status, protocol.STATUS_OK)
        ok &= _check("  ACK 0x39 param", ack_dm.dm_ack_param, protocol.PARAM_DIRECT_MODE)
        ok &= _check("  ACK 0x39 value", ack_dm.dm_ack_value, 0)

    status_off = protocol.parse_frame(bytes.fromhex("5a3905010040000000" + "00" * 55))
    if status_off is None:
        print("0x39 status response         : decoding FAILED")
        ok = False
    else:
        print(f"Decoded 0x39 status response : {status_off.describe()}")
        ok &= _check("  status -> enabled", status_off.direct_mode_enabled, False)

    # Same response with bit 0x20 set -> Direct Mode active.
    status_on = protocol.parse_frame(bytes.fromhex("5a3905012040000000" + "00" * 55))
    ok &= _check("  status (bit 0x20)",
                 status_on.direct_mode_enabled if status_on else None, True)

    print()
    samples = [
        "5a020a26000702000100" + "00" * 54,
        "5a110e02009600000000009609000000" + "00" * 48,
        "5a113208009600000000009607000000009602000000009618000000009604000000009605a4703d3f960900000000960a0000000000000000000000",
        "5a1a020000" + "00" * 59,
    ]
    for sample in samples:
        frame = protocol.parse_frame(bytes.fromhex(sample))
        print(f"decoded: {frame.describe() if frame else 'FAILED'}")
        ok = ok and frame is not None

    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="HID diagnostic for the Creative Sound Blaster G8",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--backend", action="store_true",
                        help="show the selected hidapi backend")
    parser.add_argument("--list", action="store_true", help="list the HID interfaces")
    parser.add_argument("--scout", metavar="on|off", help="enable/disable Scout Mode")
    parser.add_argument("--direct", metavar="on|off", help="enable/disable Direct Mode")
    parser.add_argument("--direct-status", action="store_true",
                        help="read Direct Mode's state from the card")
    parser.add_argument("--reconnect-test", type=int, metavar="N",
                        help="chain N Direct Mode toggles")
    parser.add_argument("--set", metavar="F:P=V", help="write a parameter (e.g. 07:0002=1)")
    parser.add_argument("--list-sound-modes", action="store_true",
                        help="list the available sound modes")
    parser.add_argument("--sound-mode", metavar="SLUG",
                        help="apply a sound mode (see --list-sound-modes)")
    parser.add_argument("--raw", nargs=2, metavar=("TYPE", "PAYLOAD"),
                        help="send an arbitrary frame (hex)")
    parser.add_argument("--monitor", action="store_true",
                        help="listen to the card's notifications")
    parser.add_argument("--duration", type=float, default=60.0,
                        help="listening duration in seconds (default: 60)")
    parser.add_argument("--selftest", action="store_true",
                        help="check encoding/decoding against the pcap (no hardware needed)")
    parser.add_argument("--debug", action="store_true", help="verbose logging")

    args = parser.parse_args()

    if args.selftest:
        return cmd_selftest()
    if args.backend:
        return cmd_backend()
    if args.list:
        return cmd_list()
    if args.list_sound_modes:
        return cmd_list_sound_modes()

    needs_hardware = (
        args.scout or args.direct or args.direct_status
        or args.reconnect_test or args.set or args.raw or args.monitor
        or args.sound_mode
    )
    if not needs_hardware:
        parser.print_help()
        return 0

    driver = SoundBlasterG8Driver(debug=args.debug, allow_simulation=False)
    try:
        driver.connect()
    except SoundBlasterG8Error as exc:
        print(f"Unable to connect: {exc}")
        return 1

    try:
        if args.scout:
            return cmd_scout(driver, args.scout)
        if args.direct:
            return cmd_direct(driver, args.direct)
        if args.direct_status:
            return cmd_direct_status(driver)
        if args.reconnect_test:
            return cmd_reconnect_test(driver, args.reconnect_test)
        if args.set:
            return cmd_set(driver, args.set)
        if args.raw:
            return cmd_raw(driver, args.raw[0], args.raw[1])
        if args.monitor:
            return cmd_monitor(driver, args.duration)
        if args.sound_mode:
            return cmd_sound_mode(driver, args.sound_mode)
    finally:
        driver.disconnect()

    return 0


if __name__ == "__main__":
    sys.exit(main())
