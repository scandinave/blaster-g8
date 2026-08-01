#!/usr/bin/env python3
"""
Outil de diagnostic et de reverse engineering pour la Sound Blaster G8.

Exemples
--------
Afficher le backend hidapi retenu (hidraw / libusb / iokit) ::

    python tools/g8_probe.py --backend

Lister les interfaces HID et leurs descripteurs ::

    python tools/g8_probe.py --list

Activer / désactiver le Scout Mode (test de bout en bout, sans GUI) ::

    python tools/g8_probe.py --scout on
    python tools/g8_probe.py --scout off

Activer / désactiver le Direct Mode, puis relire l'état matériel ::

    python tools/g8_probe.py --direct on --debug
    python tools/g8_probe.py --direct-status
    python tools/g8_probe.py --direct off --debug

Enchaîner N bascules du Direct Mode dans un seul process (valide la
reconnexion après le reset USB) ::

    python tools/g8_probe.py --reconnect-test 5

Écouter les notifications de la carte (utile pendant qu'on manipule
l'application Creative officielle, pour découvrir de nouveaux paramètres) ::

    python tools/g8_probe.py --monitor

Envoyer une trame arbitraire (type + payload en hexadécimal) ::

    python tools/g8_probe.py --raw 26 0702000100

Balayer les valeurs d'un paramètre pour identifier une fonction ::

    python tools/g8_probe.py --set 07:0002=1
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Permet l'exécution directe depuis le dépôt sans installation préalable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from soundblaster_g8 import hidbackend, protocol  # noqa: E402
from soundblaster_g8.driver import (  # noqa: E402
    SoundBlasterG8Driver,
    SoundBlasterG8Error,
)


def _truthy(value: str) -> bool:
    return value.lower() in ("on", "1", "true", "yes", "oui")


def cmd_backend() -> int:
    """Affiche le backend hidapi retenu et les modules disponibles."""
    print(f"Plateforme        : {sys.platform}")
    try:
        info = hidbackend.get_backend()
    except ImportError as exc:
        print(f"Backend HID       : AUCUN ({exc})")
        return 1

    print(f"Backend retenu    : {info.name}")
    print(f"Module            : {info.module.__name__}")
    print(f"usage_page énuméré: {'oui' if info.provides_usage_page else 'non'}")

    if sys.platform.startswith("linux"):
        for name in ("hidraw", "hid"):
            try:
                __import__(name)
                state = "disponible"
            except ImportError:
                state = "absent"
            print(f"  module {name:<7}: {state}")
        if info.name == "libusb":
            print()
            print("Note : avec libusb, usage_page vaut toujours 0 dans")
            print("hid_enumerate ; la sélection de l'interface de contrôle se")
            print("fait sur interface_number == 4. Pour forcer hidraw :")
            print("  HIDAPI_WITH_HIDRAW=1 pip install --no-binary :all: hidapi")
    return 0


def cmd_list() -> int:
    """Affiche les interfaces HID exposées par la carte."""
    interfaces = SoundBlasterG8Driver.list_interfaces()
    if not interfaces:
        print("Aucune interface HID trouvée (carte débranchée ou droits insuffisants).")
        return 1

    print(f"Backend : {SoundBlasterG8Driver.backend_name()}")
    print(f"{len(interfaces)} interface(s) HID trouvée(s) :\n")
    selected = SoundBlasterG8Driver._select_control_interface(interfaces)
    for info in interfaces:
        usage_page = info.get("usage_page", 0)
        marker = "  <== canal de contrôle" if info is selected else ""
        print(f"- interface_number : {info.get('interface_number')}{marker}")
        print(f"  usage_page       : 0x{usage_page:04x}")
        print(f"  usage            : 0x{info.get('usage', 0):04x}")
        print(f"  input_report_len : {info.get('input_report_length')}")
        print(f"  produit          : {info.get('product_string')}")
        print(f"  série            : {info.get('serial_number')}")
        print(f"  path             : {info.get('path')}")
        print()
    return 0


def cmd_scout(driver: SoundBlasterG8Driver, value: str) -> int:
    enabled = _truthy(value)
    ok = driver.set_scout_mode(enabled)
    print()
    print(f"Résultat : {'SUCCÈS' if ok else 'ÉCHEC'}")
    print(f"État connu du Scout Mode : {driver.get_scout_mode()}")
    return 0 if ok else 1


def cmd_direct(driver: SoundBlasterG8Driver, value: str) -> int:
    enabled = _truthy(value)
    ok = driver.set_direct_mode(enabled)
    print()
    print(f"Résultat : {'SUCCÈS' if ok else 'ÉCHEC'}")
    print(f"État relu sur la carte : {driver.get_direct_mode()}")
    return 0 if ok else 1


def cmd_direct_status(driver: SoundBlasterG8Driver) -> int:
    """Interroge la carte sur l'état du Direct Mode (requête 0x39)."""
    state = driver.get_direct_mode()
    if state is None:
        print("Direct Mode : état indéterminé (aucune réponse de la carte)")
        return 1
    print(f"Direct Mode : {'ACTIVÉ' if state else 'désactivé'}")
    return 0


def cmd_reconnect_test(driver: SoundBlasterG8Driver, count: int) -> int:
    """Enchaîne N bascules du Direct Mode dans un seul process.

    Chaque bascule provoque un reset USB : ce test valide que le driver
    retrouve la carte et reste utilisable, y compris après plusieurs cycles.
    """
    initial = driver.get_direct_mode()
    print(f"État initial du Direct Mode : {initial}")
    target = bool(initial) if initial is not None else False

    failures = 0
    for i in range(1, count + 1):
        target = not target
        print(f"\n=== Bascule {i}/{count} : Direct Mode -> {'ON' if target else 'OFF'} ===")
        started = time.monotonic()
        ok = driver.set_direct_mode(target)
        elapsed = time.monotonic() - started
        state = driver.get_direct_mode()
        coherent = state is None or state == target
        print(
            f"  résultat={'SUCCÈS' if ok else 'ÉCHEC'} "
            f"état relu={state} ({'cohérent' if coherent else 'INCOHÉRENT'}) "
            f"durée={elapsed:.2f}s"
        )
        if not ok or not coherent:
            failures += 1

    print(f"\n{count - failures}/{count} bascule(s) réussie(s).")
    if initial is not None and bool(initial) != target:
        print("Remise dans l'état initial...")
        driver.set_direct_mode(bool(initial))
    return 0 if failures == 0 else 1


def cmd_set(driver: SoundBlasterG8Driver, spec: str) -> int:
    """``--set feature:param=value`` (valeurs en hexa ou décimal)."""
    try:
        target, raw_value = spec.split("=", 1)
        feature_str, param_str = target.split(":", 1)
        feature = int(feature_str, 0) if feature_str.startswith("0x") else int(feature_str, 16)
        param = int(param_str, 0) if param_str.startswith("0x") else int(param_str, 16)
        value = int(raw_value, 0)
    except ValueError:
        print("Format attendu : --set 07:0002=1 (feature:param en hexa, valeur décimale)")
        return 2

    ok = driver.set_feature_u16(feature, param, value)
    print(f"Résultat : {'SUCCÈS' if ok else 'ÉCHEC'}")
    return 0 if ok else 1


def cmd_raw(driver: SoundBlasterG8Driver, frame_type: str, payload_hex: str) -> int:
    try:
        ftype = int(frame_type, 16)
        payload = bytes.fromhex(payload_hex)
    except ValueError:
        print("Format attendu : --raw 26 0702000100")
        return 2

    try:
        ack = driver.send_frame(ftype, payload)
    except SoundBlasterG8Error as exc:
        print(f"ERREUR : {exc}")
        return 1

    print(f"ACK : {ack.describe() if ack else 'aucun'}")
    return 0


def cmd_monitor(driver: SoundBlasterG8Driver, duration: float) -> int:
    """Écoute les notifications spontanées de la carte."""
    print(
        f"Écoute des notifications pendant {duration:.0f}s "
        "(Ctrl+C pour arrêter). Manipulez l'application Creative maintenant.\n"
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
        print("\nInterrompu.")

    print(f"\n{count} notification(s) reçue(s).")
    print("Paramètres connus :", driver.get_debug_info()["known_params"])
    return 0


def _check(label: str, got, expected) -> bool:
    ok = got == expected
    print(f"{label:<28}: {got} (attendu {expected}) {'OK' if ok else 'KO'}")
    return ok


def cmd_selftest() -> int:
    """Vérifie l'encodage des trames contre les octets réellement capturés."""
    ok = True

    # --- Encodage (vecteurs issus des captures USB) ---
    ok &= _check("Scout ON", protocol.build_scout_mode(True).hex(), "5a26050702000100")
    ok &= _check("Scout OFF", protocol.build_scout_mode(False).hex(), "5a26050702000000")
    ok &= _check("Direct ON", protocol.build_direct_mode(True).hex(), "5a3903000501")
    ok &= _check("Direct OFF", protocol.build_direct_mode(False).hex(), "5a3903000500")
    ok &= _check("Direct status (req)",
                 protocol.build_direct_mode_status().hex(), "5a39050120000000")
    ok &= _check("Sonde info", protocol.build_info_probe().hex(), "5a090102")

    # Trame Direct Mode OFF telle qu'elle part sur le fil : 64 octets paddés,
    # précédés du report ID 0x00 (wValue=0x0200, wLength=64).
    padded = protocol.pad_report(protocol.build_direct_mode(False))
    ok &= _check("Padding rapport", len(padded), protocol.REPORT_SIZE)
    ok &= _check("Direct OFF paddé", padded.hex(), "5a3903000500" + "00" * 58)

    print()

    # --- Décodage des trames réellement observées ---
    ack_dm = protocol.parse_frame(bytes.fromhex("5a020a390005000000000000" + "00" * 52))
    if ack_dm is None:
        print("ACK 0x39                    : ÉCHEC de décodage KO")
        ok = False
    else:
        print(f"ACK 0x39 décodé             : {ack_dm.describe()}")
        ok &= _check("  ACK 0x39 cmd", ack_dm.ack_command, protocol.CMD_DIRECT_MODE)
        ok &= _check("  ACK 0x39 status", ack_dm.ack_status, protocol.STATUS_OK)
        ok &= _check("  ACK 0x39 param", ack_dm.dm_ack_param, protocol.PARAM_DIRECT_MODE)
        ok &= _check("  ACK 0x39 value", ack_dm.dm_ack_value, 0)

    status_off = protocol.parse_frame(bytes.fromhex("5a3905010040000000" + "00" * 55))
    if status_off is None:
        print("Réponse status 0x39         : ÉCHEC de décodage KO")
        ok = False
    else:
        print(f"Réponse status 0x39 décodée : {status_off.describe()}")
        ok &= _check("  status -> enabled", status_off.direct_mode_enabled, False)

    # Même réponse avec le bit 0x20 positionné -> Direct Mode actif.
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
        print(f"décodé : {frame.describe() if frame else 'ÉCHEC'}")
        ok = ok and frame is not None

    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diagnostic HID de la Creative Sound Blaster G8",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--backend", action="store_true",
                        help="afficher le backend hidapi retenu")
    parser.add_argument("--list", action="store_true", help="lister les interfaces HID")
    parser.add_argument("--scout", metavar="on|off", help="activer/désactiver le Scout Mode")
    parser.add_argument("--direct", metavar="on|off", help="activer/désactiver le Direct Mode")
    parser.add_argument("--direct-status", action="store_true",
                        help="lire l'état du Direct Mode sur la carte")
    parser.add_argument("--reconnect-test", type=int, metavar="N",
                        help="enchaîner N bascules du Direct Mode")
    parser.add_argument("--set", metavar="F:P=V", help="écrire un paramètre (ex. 07:0002=1)")
    parser.add_argument("--raw", nargs=2, metavar=("TYPE", "PAYLOAD"),
                        help="envoyer une trame arbitraire (hexa)")
    parser.add_argument("--monitor", action="store_true",
                        help="écouter les notifications de la carte")
    parser.add_argument("--duration", type=float, default=60.0,
                        help="durée d'écoute en secondes (défaut: 60)")
    parser.add_argument("--selftest", action="store_true",
                        help="vérifier l'encodage/décodage contre le pcap (sans matériel)")
    parser.add_argument("--debug", action="store_true", help="traces détaillées")

    args = parser.parse_args()

    if args.selftest:
        return cmd_selftest()
    if args.backend:
        return cmd_backend()
    if args.list:
        return cmd_list()

    needs_hardware = (
        args.scout or args.direct or args.direct_status
        or args.reconnect_test or args.set or args.raw or args.monitor
    )
    if not needs_hardware:
        parser.print_help()
        return 0

    driver = SoundBlasterG8Driver(debug=args.debug, allow_simulation=False)
    try:
        driver.connect()
    except SoundBlasterG8Error as exc:
        print(f"Connexion impossible : {exc}")
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
    finally:
        driver.disconnect()

    return 0


if __name__ == "__main__":
    sys.exit(main())
