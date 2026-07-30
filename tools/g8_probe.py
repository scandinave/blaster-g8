#!/usr/bin/env python3
"""
Outil de diagnostic et de reverse engineering pour la Sound Blaster G8.

Exemples
--------
Lister les interfaces HID et leurs descripteurs ::

    python tools/g8_probe.py --list

Activer / désactiver le Scout Mode (test de bout en bout, sans GUI) ::

    python tools/g8_probe.py --scout on
    python tools/g8_probe.py --scout off

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

from soundblaster_g8 import protocol  # noqa: E402
from soundblaster_g8.driver import (  # noqa: E402
    SoundBlasterG8Driver,
    SoundBlasterG8Error,
)


def cmd_list() -> int:
    """Affiche les interfaces HID exposées par la carte."""
    interfaces = SoundBlasterG8Driver.list_interfaces()
    if not interfaces:
        print("Aucune interface HID trouvée (carte débranchée ou droits insuffisants).")
        return 1

    print(f"{len(interfaces)} interface(s) HID trouvée(s) :\n")
    for info in interfaces:
        usage_page = info.get("usage_page", 0)
        is_control = usage_page == 0xFF01
        marker = "  <== canal de contrôle" if is_control else ""
        print(f"- interface_number : {info.get('interface_number')}{marker}")
        print(f"  usage_page       : 0x{usage_page:04x}")
        print(f"  usage            : 0x{info.get('usage', 0):04x}")
        print(f"  produit          : {info.get('product_string')}")
        print(f"  série            : {info.get('serial_number')}")
        print(f"  path             : {info.get('path')}")
        print()
    return 0


def cmd_scout(driver: SoundBlasterG8Driver, value: str) -> int:
    enabled = value.lower() in ("on", "1", "true", "yes", "oui")
    ok = driver.set_scout_mode(enabled)
    print()
    print(f"Résultat : {'SUCCÈS' if ok else 'ÉCHEC'}")
    print(f"État connu du Scout Mode : {driver.get_scout_mode()}")
    return 0 if ok else 1


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


def cmd_selftest() -> int:
    """Vérifie l'encodage des trames contre les octets réellement capturés."""
    expected_on = "5a26050702000100"
    expected_off = "5a26050702000000"
    got_on = protocol.build_scout_mode(True).hex()
    got_off = protocol.build_scout_mode(False).hex()

    ok = got_on == expected_on and got_off == expected_off
    print(f"Scout ON  : {got_on} (attendu {expected_on}) {'OK' if got_on == expected_on else 'KO'}")
    print(f"Scout OFF : {got_off} (attendu {expected_off}) {'OK' if got_off == expected_off else 'KO'}")

    # Décodage des notifications réellement observées dans le pcap
    samples = [
        "5a020a26000702000100" + "00" * 54,
        "5a110e02009600000000009609000000" + "00" * 48,
        "5a113208009600000000009607000000009602000000009618000000009604000000009605a4703d3f960900000000960a0000000000000000000000",
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
    parser.add_argument("--list", action="store_true", help="lister les interfaces HID")
    parser.add_argument("--scout", metavar="on|off", help="activer/désactiver le Scout Mode")
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
    if args.list:
        return cmd_list()

    if not (args.scout or args.set or args.raw or args.monitor):
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
