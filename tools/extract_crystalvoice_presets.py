#!/usr/bin/env python3
"""
Generates ``soundblaster_g8/crystalvoice_presets.py`` from the CrystalVoice USB
captures (one ``.pcapng`` capture per preset, see ``soundblaster_g8/protocol.py``
for the CMD_SET_FLOAT frame format and the TLV_CRYSTALVOICE marker).

Two families of captures are consumed:

* ``CrystalVoice-VoiceMorph-<name>.pcapng``     -> 8 writes, params 0x0b..0x12
* ``CrystalVoice-MicroEqualizer-<name>.pcapng`` -> 10 writes, params 0x14..0x1d

The on/off captures (``CrystalVoice-VoiceMorph.pcapng``,
``CrystalVoice-MicroEqualizerOnOff.pcapng``) only toggle params 0x0a / 0x13 and
are not presets: they are excluded.

Development tool: not used by the application at runtime (no dependency on
``tshark`` or ``.pcapng`` files outside of this generation step). Re-run it
if new captures are provided.

Usage::

    python tools/extract_crystalvoice_presets.py --input ~/Documents/pcap
"""

from __future__ import annotations

import argparse
import struct
import subprocess
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from soundblaster_g8 import protocol  # noqa: E402

VOICE_MORPH_PREFIX = "CrystalVoice-VoiceMorph-"
MIC_EQ_PREFIX = "CrystalVoice-MicroEqualizer-"

#: On/off captures: they write the enable bit (0x0a / 0x13), not a preset.
EXCLUDED_FILENAMES = {
    "CrystalVoice-VoiceMorph.pcapng",
    "CrystalVoice-MicroEqualizerOnOff.pcapng",
}

DEFAULT_VOICE_MORPH = "neutral"
DEFAULT_MIC_EQ = "equilibre"

#: English display labels, keyed by slug. The captures come from the French
#: Creative application, so the filenames (hence the slugs) are a mix of
#: French and English: the labels below are the single source of truth for
#: what the GUI shows. Translations live in the gettext catalogs, keyed
#: ``crystalvoice_preset.<slug>`` (see ``gui/i18n.crystalvoice_preset_label``).
#: A capture whose slug is missing here is skipped with a warning, so new
#: captures fail loudly rather than showing a raw slug.
LABELS: dict[str, str] = {
    # Voice Morph
    "neutral": "Neutral",
    "men": "Man",
    "women": "Woman",
    "child": "Child",
    "old-people": "Elderly",
    "chipmink": "Chipmunk",
    "deepvoice": "Deep Voice",
    "demon": "Demon",
    "emo": "Emo",
    "orc": "Orc",
    "robot": "Robot",
    "nain": "Dwarf",
    "lutin": "Goblin",
    "marin": "Sailor",
    "brutable": "Brute",
    "instable": "Unstable",
    "agent-infiltre": "Undercover Agent",
    "from-the-north": "Nordic",
    # Microphone Equalizer
    "equilibre": "Balanced",
    "clarte-des-voix": "Vocal Clarity",
    "chaleur-vocale": "Vocal Warmth",
    "annonce-publique": "Public Address",
    "broadcast": "Broadcast",
    "communication": "Communication",
    "enregistrement": "Recording",
    "pitch-boost": "Pitch Boost",
    "pitch-reduction": "Pitch Reduction",
}


def slugify(name: str) -> str:
    """ASCII slug from a capture's preset name (``clarté-des-voix`` -> ``clarte-des-voix``)."""
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def extract_writes(path: Path) -> list[tuple[int, float]]:
    """Returns the ``(param, value)`` CrystalVoice writes of a capture, in order.

    Unlike ``extract_sound_modes.py`` (which reads tshark's hex dump at a fixed
    USBPcap offset), the SET_REPORT payload is read straight from the
    ``usb.data_fragment`` field: tshark already strips the pseudo-header and
    the setup packet, so the value is the 64-byte report itself.
    """
    result = subprocess.run(
        ["tshark", "-r", str(path), "-T", "fields", "-e", "usb.data_fragment"],
        capture_output=True, text=True, check=True,
    )

    writes: list[tuple[int, float]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        report = bytes.fromhex(line)
        if len(report) < protocol.HEADER_SIZE or report[0] != protocol.MAGIC:
            continue
        frame_type, length = report[1], report[2]
        payload = report[protocol.HEADER_SIZE:protocol.HEADER_SIZE + length]
        if frame_type != protocol.CMD_SET_FLOAT or len(payload) != 7:
            continue
        prefix, marker, param = payload[0], payload[1], payload[2]
        if prefix != protocol.SET_FLOAT_PREFIX or marker != protocol.TLV_CRYSTALVOICE:
            continue
        writes.append((param, struct.unpack("<f", payload[3:7])[0]))
    return writes


def collect(
    pcap_files: list[Path], prefix: str, expected_params: tuple[int, ...], default_slug: str,
) -> list[tuple[str, str, list[tuple[int, float]]]]:
    """Decodes every capture of one family into ``(slug, label, writes)`` entries."""
    entries: list[tuple[str, str, list[tuple[int, float]]]] = []
    for path in pcap_files:
        if not path.name.startswith(prefix):
            continue
        writes = extract_writes(path)
        by_param = dict(writes)
        missing = [f"0x{p:02x}" for p in expected_params if p not in by_param]
        if missing:
            print(f"WARNING: {path.name} - incomplete capture (missing params: {missing}), skipped")
            continue
        slug = slugify(path.stem[len(prefix):])
        label = LABELS.get(slug)
        if label is None:
            print(f"WARNING: {path.name} - no label defined for slug {slug!r}, skipped")
            continue
        entries.append((slug, label, writes))
        print(f"  {path.name:<50} -> slug={slug!r:<20} ({len(writes)} writes)")

    # Default preset first, then alphabetical order by label.
    entries.sort(key=lambda e: (e[0] != default_slug, e[1]))
    return entries


def format_writes(writes: list[tuple[int, float]]) -> str:
    return "(" + ", ".join(f"(0x{p:02x}, {v!r})" for p, v in writes) + ")"


def format_dict(name: str, entries: list[tuple[str, str, list[tuple[int, float]]]]) -> list[str]:
    lines = [f"{name}: dict[str, CrystalVoicePreset] = {{"]
    for slug, label, writes in entries:
        lines.append(f"    {slug!r}: CrystalVoicePreset(")
        lines.append(f"        slug={slug!r},")
        lines.append(f"        label={label!r},")
        lines.append(f"        writes={format_writes(writes)},")
        lines.append("    ),")
    lines.append("}")
    return lines


def generate(input_dir: Path, output_path: Path) -> None:
    pcap_files = sorted(
        p for p in input_dir.glob("CrystalVoice-*.pcapng") if p.name not in EXCLUDED_FILENAMES
    )
    if not pcap_files:
        raise SystemExit(f"No CrystalVoice-*.pcapng file found in {input_dir}")

    print("Voice Morph:")
    voice_morph = collect(
        pcap_files, VOICE_MORPH_PREFIX, protocol.CV_VOICE_MORPH_PARAMS, DEFAULT_VOICE_MORPH,
    )
    print("Microphone Equalizer:")
    mic_eq = collect(
        pcap_files, MIC_EQ_PREFIX, protocol.CV_MIC_EQ_BAND_PARAMS, DEFAULT_MIC_EQ,
    )
    if not voice_morph or not mic_eq:
        raise SystemExit("At least one family has no usable capture, aborting")

    lines = [
        '"""',
        "Sound Blaster G8 CrystalVoice presets, generated from USB captures.",
        "",
        f"Generated by ``tools/extract_crystalvoice_presets.py`` from {len(voice_morph)}",
        f"Voice Morph and {len(mic_eq)} Microphone Equalizer capture(s). Do not edit by",
        "hand: re-run the script if new captures are provided.",
        "",
        "Both features are replayed like a sound mode (an ordered sequence of",
        "CMD_SET_FLOAT writes), but with the TLV_CRYSTALVOICE marker - see",
        "``soundblaster_g8/protocol.py``. The enable bit (param 0x0a for Voice Morph,",
        "0x13 for the Microphone Equalizer) is not part of a preset: the official",
        "application never rewrites it when switching presets.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass",
        "",
        "",
        "@dataclass(frozen=True)",
        "class CrystalVoicePreset:",
        '    """A CrystalVoice preset: sequence of CMD_SET_FLOAT frames to replay."""',
        "",
        "    slug: str",
        "    label: str",
        "    #: Ordered sequence (param_id, value) - capture order preserved.",
        "    writes: tuple[tuple[int, float], ...]",
        "",
        "",
        f"DEFAULT_VOICE_MORPH = {DEFAULT_VOICE_MORPH!r}",
        f"DEFAULT_MIC_EQ = {DEFAULT_MIC_EQ!r}",
        "",
    ]
    lines += format_dict("VOICE_MORPH_PRESETS", voice_morph)
    lines.append("")
    lines += format_dict("MIC_EQ_PRESETS", mic_eq)
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(
        f"\n{len(voice_morph)} Voice Morph + {len(mic_eq)} Microphone Equalizer "
        f"preset(s) written to {output_path}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", required=True, type=Path,
        help="folder containing the CrystalVoice-*.pcapng captures",
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parent.parent / "soundblaster_g8" / "crystalvoice_presets.py",
        help="generated Python file (default: soundblaster_g8/crystalvoice_presets.py)",
    )
    args = parser.parse_args()

    input_dir = args.input.expanduser()
    if not input_dir.is_dir():
        raise SystemExit(f"Folder not found: {input_dir}")

    generate(input_dir, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
