"""Compile the .po translation catalogs under soundblaster_g8/locale/ into .mo.

Run this after editing any .po file:

    python tools/compile_translations.py

Requires the GNU gettext ``msgfmt`` binary (package ``gettext`` on most
distros, part of Xcode command line tools on macOS). The compiled .mo files
are build artifacts (gitignored), not source - they are what
``soundblaster_g8.gui.i18n`` actually loads at runtime.
"""

import shutil
import subprocess
import sys
from pathlib import Path

LOCALE_DIR = Path(__file__).resolve().parent.parent / "soundblaster_g8" / "locale"


def main() -> int:
    if shutil.which("msgfmt") is None:
        print(
            "error: msgfmt not found (install the 'gettext' package)",
            file=sys.stderr,
        )
        return 1

    po_files = sorted(LOCALE_DIR.glob("*/LC_MESSAGES/*.po"))
    if not po_files:
        print(f"error: no .po files found under {LOCALE_DIR}", file=sys.stderr)
        return 1

    for po_path in po_files:
        mo_path = po_path.with_suffix(".mo")
        result = subprocess.run(
            ["msgfmt", "--check", str(po_path), "-o", str(mo_path)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"error: failed to compile {po_path}:\n{result.stderr}", file=sys.stderr)
            return 1
        print(f"compiled {po_path.relative_to(LOCALE_DIR.parent.parent)} -> {mo_path.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
