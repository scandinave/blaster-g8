"""Rasterize the bundled Bootstrap Icons into soundblaster_g8/gui/icon_data.py.

Run this after adding, removing or replacing an .svg under
assets/bootstrap-icons/:

    pip install cairosvg     # or: pip install -e '.[build]'
    python tools/build_icons.py

Requires ``cairosvg`` - the same kind of build-time dependency as ``msgfmt``
for the translations. The generated module *is* committed, so contributors who
don't touch the icons never need it. cairosvg is a pip install on both Linux
and macOS (it needs the cairo library, already present on any desktop Linux,
``brew install cairo`` on macOS).

ImageMagick's built-in SVG renderer was tried first, since it needs no Python
package, and it is **not** usable here: it merges the sub-paths of a compound
path, which turns ``soundwave`` - seven separate bars in one ``<path>`` - into
a solid diamond. It gets simpler glyphs right, so the breakage is silent; hence
cairosvg, which renders the whole set correctly.

Each icon is stored as a plain 8-bit **alpha mask** (one byte of coverage per
pixel), not as a picture: the GUI tints it at runtime to whatever colour the
widget's state calls for (see ``soundblaster_g8/gui/icons.py``). Bootstrap's
SVGs are single-colour with ``fill="currentColor"``, so the shape is all the
information there is to keep.
"""

import base64
import io
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SVG_DIR = ROOT / "assets" / "bootstrap-icons"
OUTPUT = ROOT / "soundblaster_g8" / "gui" / "icon_data.py"

#: Pixel sizes to pre-render: 15 px for RoundedButton, 18 px for the sidebar
#: rows and the volume rows, 22 px for the 36 px icon badges. 14 and 16 are
#: there so a glyph's balance inside its box can be adjusted without needing
#: cairosvg again.
SIZES = (14, 15, 16, 18, 22)

#: Bootstrap Icons release the .svg files were taken from (see the sibling
#: README.md); recorded in the generated module for traceability.
BOOTSTRAP_ICONS_VERSION = "1.13.1"

HEADER = '''"""Alpha masks for the bundled Bootstrap Icons - GENERATED FILE, DO NOT EDIT.

Regenerate with ``python tools/build_icons.py`` after changing anything under
``assets/bootstrap-icons/``.

Source: Bootstrap Icons v{version} (MIT), vendored under
``assets/bootstrap-icons/``. Each entry is one 8-bit alpha mask per size,
zlib-compressed then base85-encoded: ``MASKS[icon][size]`` holds ``size *
size`` bytes of coverage, row by row, which :mod:`soundblaster_g8.gui.icons`
tints at runtime.
"""

import base64
import zlib

BOOTSTRAP_ICONS_VERSION = "{version}"

#: Pixel sizes available for every icon.
SIZES = {sizes}

_PACKED: dict[str, dict[int, str]] = {{
'''

FOOTER = '''}}

#: ``{{icon name: {{size: alpha mask}}}}``, unpacked once at import.
MASKS: dict[str, dict[int, bytes]] = {{
    name: {{size: zlib.decompress(base64.b85decode(packed)) for size, packed in by_size.items()}}
    for name, by_size in _PACKED.items()
}}
'''


def rasterize(svg_path: Path, size: int) -> bytes:
    """Returns ``size * size`` bytes of alpha coverage for one icon.

    Bootstrap ships its glyphs as ``fill="currentColor"``, which only means
    something in a document with a colour to inherit; cairosvg resolves it to
    black. That's fine - only the alpha channel is kept, and the GUI supplies
    the colour.
    """
    import cairosvg  # imported here so --help/-style errors don't need it
    from PIL import Image

    png = cairosvg.svg2png(
        url=str(svg_path), output_width=size, output_height=size,
    )
    image = Image.open(io.BytesIO(png)).convert("RGBA")
    if image.size != (size, size):
        raise RuntimeError(
            f"{svg_path.name}: expected a {size}x{size} render, got {image.size}"
        )
    mask = image.getchannel("A").tobytes()
    if not any(mask):
        # An empty mask means the glyph didn't draw at all: better to stop
        # than to ship an icon that silently disappears from the interface.
        raise RuntimeError(f"{svg_path.name} at {size}px rendered empty")
    return mask


def main() -> int:
    try:
        import cairosvg  # noqa: F401 - availability check only
    except ImportError:
        print(
            "error: cairosvg not found (pip install cairosvg; needs the cairo "
            "library, 'brew install cairo' on macOS)",
            file=sys.stderr,
        )
        return 1

    svg_files = sorted(SVG_DIR.glob("*.svg"))
    if not svg_files:
        print(f"error: no .svg files found under {SVG_DIR}", file=sys.stderr)
        return 1

    packed: dict[str, dict[int, str]] = {}
    for svg_path in svg_files:
        by_size = {}
        for size in SIZES:
            try:
                mask = rasterize(svg_path, size)
            except RuntimeError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            by_size[size] = base64.b85encode(zlib.compress(mask, 9)).decode("ascii")
        packed[svg_path.stem] = by_size
        print(f"rendered {svg_path.name} at {', '.join(f'{s}px' for s in SIZES)}")

    lines = [HEADER.format(version=BOOTSTRAP_ICONS_VERSION, sizes=SIZES)]
    for name, by_size in packed.items():
        lines.append(f'    "{name}": {{\n')
        for size, blob in by_size.items():
            lines.append(f'        {size}: "{blob}",\n')
        lines.append("    },\n")
    lines.append(FOOTER.format())

    OUTPUT.write_text("".join(lines), encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)} ({len(packed)} icons, {OUTPUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
