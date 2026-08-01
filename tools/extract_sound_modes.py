#!/usr/bin/env python3
"""
Génère ``soundblaster_g8/sound_modes.py`` à partir des captures USB
« Sound Mode » (une capture ``.pcapng`` par mode, voir
``soundblaster_g8/protocol.py`` pour le format des trames CMD_SET_FLOAT).

Outil de développement : il n'est pas utilisé par l'application au runtime
(pas de dépendance à ``tshark`` ni aux fichiers ``.pcapng`` en dehors de
cette génération). À relancer si de nouvelles captures sont fournies.

Utilisation ::

    python tools/extract_sound_modes.py --input "~/Documents/Sound Blaster G8/SoundMode"
"""

from __future__ import annotations

import argparse
import re
import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from soundblaster_g8 import protocol  # noqa: E402

# Offset du payload utile dans une trame "SET_REPORT Request" telle que
# capturée par USBPcap : 28 o de pseudo-header + 8 o de Setup Data.
PAYLOAD_OFFSET = 36
REPORT_SIZE = 64

# Fichier de capture qui n'est pas un mode (juste un bascule on/off de
# l'égaliseur maître) : exclu de la génération.
EXCLUDED_FILENAMES = {"Equalizer.pcapng"}

# Capture correspondant au mode par défaut (aucun égaliseur actif).
DEFAULT_SOURCE = "Equalizer-effects-disabled.pcapng"
DEFAULT_SLUG = "disabled"
DEFAULT_LABEL = "Désactivé"

ACRONYMS = {
    "cs2", "csgo", "fps", "rpg", "rts", "moba", "mmorpg", "pubg", "sbx",
}

HEX_LINE_RE = re.compile(r"^[0-9a-f]{4}  ((?:[0-9a-f]{2} ?){1,16})")


def slug_from_filename(path: Path) -> str:
    if path.name == DEFAULT_SOURCE:
        return DEFAULT_SLUG
    name = path.stem
    if name.startswith("Equalizer-"):
        name = name[len("Equalizer-"):]
    return name


def label_from_slug(slug: str) -> str:
    if slug == DEFAULT_SLUG:
        return DEFAULT_LABEL
    words = []
    for word in slug.split("-"):
        if word.lower() in ACRONYMS:
            words.append(word.upper())
        elif word.lower() == "s" and words:
            # Apostrophe possessive perdue lors du "slugify" du nom de
            # fichier ("baldur-s-gate" -> "Baldur's Gate").
            words[-1] += "'s"
        else:
            words.append(word.capitalize())
    return " ".join(words)


def extract_set_report_requests(path: Path) -> list[bytes]:
    """Retourne le payload brut (5a <type> <len> ...) de chaque écriture."""
    result = subprocess.run(
        [
            "tshark", "-r", str(path),
            "-Y", '_ws.col.info=="SET_REPORT Request"',
            "-x",
        ],
        capture_output=True, text=True, check=True,
    )
    frames: list[bytes] = []
    for block in result.stdout.split("Packet (")[1:]:
        header_block = block.split("USB Control")[0]
        hex_bytes: list[str] = []
        for line in header_block.splitlines():
            m = HEX_LINE_RE.match(line)
            if m:
                hex_bytes.extend(m.group(1).split())
        data = bytes.fromhex("".join(hex_bytes))
        payload = data[PAYLOAD_OFFSET:PAYLOAD_OFFSET + REPORT_SIZE]
        if len(payload) >= protocol.HEADER_SIZE and payload[0] == protocol.MAGIC:
            frames.append(payload)
    return frames


def decode_float_writes(frames: list[bytes]) -> list[tuple[int, float]]:
    """Ne garde que les écritures CMD_SET_FLOAT, décodées en (param, valeur)."""
    writes: list[tuple[int, float]] = []
    for raw in frames:
        frame_type = raw[1]
        length = raw[2]
        payload = raw[protocol.HEADER_SIZE:protocol.HEADER_SIZE + length]
        if frame_type != protocol.CMD_SET_FLOAT or len(payload) != 7:
            continue
        prefix, marker, param = payload[0], payload[1], payload[2]
        if prefix != protocol.SET_FLOAT_PREFIX or marker != protocol.TLV_FLOAT:
            continue
        value = struct.unpack("<f", payload[3:7])[0]
        writes.append((param, value))
    return writes


def bands_from_writes(writes: list[tuple[int, float]]) -> tuple[float, ...]:
    by_param = dict(writes)
    return tuple(by_param.get(p, 0.0) for p in protocol.EQ_BAND_PARAMS)


def format_writes(writes: list[tuple[int, float]]) -> str:
    return "(" + ", ".join(f"(0x{p:02x}, {v!r})" for p, v in writes) + ")"


def format_bands(bands: tuple[float, ...]) -> str:
    return "(" + ", ".join(repr(v) for v in bands) + ")"


def generate(input_dir: Path, output_path: Path) -> None:
    pcap_files = sorted(input_dir.glob("*.pcapng"))
    pcap_files = [p for p in pcap_files if p.name not in EXCLUDED_FILENAMES]
    if not pcap_files:
        raise SystemExit(f"Aucun fichier .pcapng trouvé dans {input_dir}")

    modes: list[tuple[str, str, list[tuple[int, float]], tuple[float, ...]]] = []
    for path in pcap_files:
        frames = extract_set_report_requests(path)
        writes = decode_float_writes(frames)
        if not writes:
            print(f"AVERTISSEMENT: aucune écriture CMD_SET_FLOAT dans {path.name}, ignoré")
            continue
        missing_bands = [
            f"0x{p:02x}" for p in protocol.EQ_BAND_PARAMS
            if p not in dict(writes)
        ]
        if missing_bands:
            print(
                f"AVERTISSEMENT: {path.name} - capture incomplète "
                f"(bandes manquantes: {missing_bands}), ignoré"
            )
            continue
        slug = slug_from_filename(path)
        label = label_from_slug(slug)
        bands = bands_from_writes(writes)
        modes.append((slug, label, writes, bands))
        print(f"  {path.name:<45} -> slug={slug!r:<25} ({len(writes)} écritures)")

    # Le mode par défaut en premier, puis ordre alphabétique du label.
    modes.sort(key=lambda m: (m[0] != DEFAULT_SLUG, m[1]))

    lines = [
        '"""',
        "Modes sonores de la Sound Blaster G8, générés depuis les captures USB.",
        "",
        f"Généré par ``tools/extract_sound_modes.py`` à partir de {len(modes)} capture(s)",
        "dans le dossier « Sound Mode ». Ne pas éditer à la main : relancer le script",
        "si de nouvelles captures sont fournies.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass",
        "",
        "",
        "@dataclass(frozen=True)",
        "class SoundMode:",
        '    """Un mode sonore : séquence de trames CMD_SET_FLOAT à rejouer."""',
        "",
        "    slug: str",
        "    label: str",
        "    #: Séquence ordonnée (param_id, valeur) - ordre de capture préservé.",
        "    writes: tuple[tuple[int, float], ...]",
        "    #: Les 10 bandes d'égaliseur, en dB (dérivées de ``writes``).",
        "    bands: tuple[float, ...]",
        "",
        "",
        f"DEFAULT_SOUND_MODE = {DEFAULT_SLUG!r}",
        "",
        "SOUND_MODES: dict[str, SoundMode] = {",
    ]
    for slug, label, writes, bands in modes:
        lines.append(f"    {slug!r}: SoundMode(")
        lines.append(f"        slug={slug!r},")
        lines.append(f"        label={label!r},")
        lines.append(f"        writes={format_writes(writes)},")
        lines.append(f"        bands={format_bands(bands)},")
        lines.append("    ),")
    lines.append("}")
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n{len(modes)} mode(s) écrit(s) dans {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", required=True, type=Path,
        help="dossier contenant les captures Equalizer-*.pcapng",
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parent.parent / "soundblaster_g8" / "sound_modes.py",
        help="fichier Python généré (défaut: soundblaster_g8/sound_modes.py)",
    )
    args = parser.parse_args()

    input_dir = args.input.expanduser()
    if not input_dir.is_dir():
        raise SystemExit(f"Dossier introuvable: {input_dir}")

    generate(input_dir, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
