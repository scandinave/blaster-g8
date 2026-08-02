#!/usr/bin/env python3
"""
Generates ``soundblaster_g8/sound_modes.py`` from the "Sound Mode" USB
captures (one ``.pcapng`` capture per mode, see ``soundblaster_g8/protocol.py``
for the CMD_SET_FLOAT frame format).

Development tool: not used by the application at runtime (no dependency on
``tshark`` or ``.pcapng`` files outside of this generation step). Re-run it
if new captures are provided.

Usage::

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

# Offset of the useful payload within a "SET_REPORT Request" frame as
# captured by USBPcap: 28 B of pseudo-header + 8 B of Setup Data.
PAYLOAD_OFFSET = 36
REPORT_SIZE = 64

# Capture files that aren't modes (just an on/off toggle of the master
# equalizer, or a calibration session of the individual sliders used to
# reverse-engineer Preamp/Bass/Treble): excluded from generation.
EXCLUDED_FILENAMES = {"Equalizer.pcapng", "Equalizer-manual.pcapng"}

# Capture matching the default mode (no equalizer active).
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
            # Possessive apostrophe lost during the filename "slugify"
            # ("baldur-s-gate" -> "Baldur's Gate").
            words[-1] += "'s"
        else:
            words.append(word.capitalize())
    return " ".join(words)


def extract_set_report_requests(path: Path) -> list[bytes]:
    """Returns the raw payload (5a <type> <len> ...) of each write."""
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
    """Keeps only CMD_SET_FLOAT writes, decoded as (param, value)."""
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


def preamp_from_writes(writes: list[tuple[int, float]]) -> float:
    return dict(writes).get(protocol.PARAM_PREAMP, 0.0)


def eq_enabled_from_writes(writes: list[tuple[int, float]]) -> bool:
    return bool(dict(writes).get(protocol.PARAM_EQ_ENABLED, 0.0))


def format_writes(writes: list[tuple[int, float]]) -> str:
    return "(" + ", ".join(f"(0x{p:02x}, {v!r})" for p, v in writes) + ")"


def format_bands(bands: tuple[float, ...]) -> str:
    return "(" + ", ".join(repr(v) for v in bands) + ")"


def generate(input_dir: Path, output_path: Path) -> None:
    pcap_files = sorted(input_dir.glob("*.pcapng"))
    pcap_files = [p for p in pcap_files if p.name not in EXCLUDED_FILENAMES]
    if not pcap_files:
        raise SystemExit(f"No .pcapng file found in {input_dir}")

    modes: list[tuple[str, str, list[tuple[int, float]], tuple[float, ...], float, bool]] = []
    for path in pcap_files:
        frames = extract_set_report_requests(path)
        writes = decode_float_writes(frames)
        if not writes:
            print(f"WARNING: no CMD_SET_FLOAT write in {path.name}, skipped")
            continue
        missing_bands = [
            f"0x{p:02x}" for p in protocol.EQ_BAND_PARAMS
            if p not in dict(writes)
        ]
        if missing_bands:
            print(
                f"WARNING: {path.name} - incomplete capture "
                f"(missing bands: {missing_bands}), skipped"
            )
            continue
        slug = slug_from_filename(path)
        label = label_from_slug(slug)
        bands = bands_from_writes(writes)
        preamp = preamp_from_writes(writes)
        eq_enabled = eq_enabled_from_writes(writes)
        modes.append((slug, label, writes, bands, preamp, eq_enabled))
        print(f"  {path.name:<45} -> slug={slug!r:<25} ({len(writes)} writes)")

    # Default mode first, then alphabetical order by label.
    modes.sort(key=lambda m: (m[0] != DEFAULT_SLUG, m[1]))

    lines = [
        '"""',
        "Sound Blaster G8 sound modes, generated from USB captures.",
        "",
        f"Generated by ``tools/extract_sound_modes.py`` from {len(modes)} capture(s)",
        "in the \"Sound Mode\" folder. Do not edit by hand: re-run the script if new",
        "captures are provided.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass",
        "",
        "",
        "@dataclass(frozen=True)",
        "class SoundMode:",
        '    """A sound mode: sequence of CMD_SET_FLOAT frames to replay."""',
        "",
        "    slug: str",
        "    label: str",
        "    #: Ordered sequence (param_id, value) - capture order preserved.",
        "    writes: tuple[tuple[int, float], ...]",
        "    #: The 10 equalizer bands, in dB (derived from ``writes``).",
        "    bands: tuple[float, ...]",
        "    #: Preamp (param 0x0a), in dB (derived from ``writes``).",
        "    preamp: float",
        "    #: Whether the equalizer is active (param 0x09, derived from ``writes``).",
        "    eq_enabled: bool",
        "",
        "",
        f"DEFAULT_SOUND_MODE = {DEFAULT_SLUG!r}",
        "",
        "SOUND_MODES: dict[str, SoundMode] = {",
    ]
    for slug, label, writes, bands, preamp, eq_enabled in modes:
        lines.append(f"    {slug!r}: SoundMode(")
        lines.append(f"        slug={slug!r},")
        lines.append(f"        label={label!r},")
        lines.append(f"        writes={format_writes(writes)},")
        lines.append(f"        bands={format_bands(bands)},")
        lines.append(f"        preamp={preamp!r},")
        lines.append(f"        eq_enabled={eq_enabled!r},")
        lines.append("    ),")
    lines.append("}")
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n{len(modes)} mode(s) written to {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", required=True, type=Path,
        help="folder containing the Equalizer-*.pcapng captures",
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parent.parent / "soundblaster_g8" / "sound_modes.py",
        help="generated Python file (default: soundblaster_g8/sound_modes.py)",
    )
    args = parser.parse_args()

    input_dir = args.input.expanduser()
    if not input_dir.is_dir():
        raise SystemExit(f"Folder not found: {input_dir}")

    generate(input_dir, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
