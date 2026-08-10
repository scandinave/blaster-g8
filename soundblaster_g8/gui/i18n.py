"""Internationalization (English/French) for the Sound Blaster G8 GUI.

Translations are standard gettext catalogs under ``soundblaster_g8/locale/``
(one ``.po``/compiled ``.mo`` pair per language, see
``tools/compile_translations.py``), not a hardcoded Python dict: adding a new
``locale/<lang>/LC_MESSAGES/soundblaster_g8.po`` (and compiling it) is enough
for that language to appear in :func:`available_languages` on next launch, no
code change required.

Call sites use ``_(message)`` with the message written in English (the
gettext convention: the literal English text doubles as both the source
string and the catalog key). Dynamic strings keep ``str.format`` placeholders
inside the message, e.g. ``_("Band {band}").format(band=freq)``.
"""

from __future__ import annotations

import gettext
import json
import os
from pathlib import Path
from typing import Callable

DOMAIN = "soundblaster_g8"
LOCALE_DIR = Path(__file__).resolve().parent.parent / "locale"
DEFAULT_LANGUAGE = "en"

#: Sound-mode display-label overrides, keyed by slug (see sound_mode_label
#: below) - only the 4 French-authored slugs among the ~51 vendor-captured
#: sound modes need one; the rest (game titles) are already language-neutral.
_SOUND_MODE_SLUGS = ("disabled", "jeux", "musique", "stade")

_current_language = DEFAULT_LANGUAGE
_listeners: list[Callable[[str], None]] = []
_translations: dict[str, gettext.NullTranslations] = {}


def _settings_path() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(config_home) / "soundblaster-g8" / "settings.json"


def _get_translation(lang: str) -> gettext.NullTranslations:
    if lang not in _translations:
        try:
            _translations[lang] = gettext.translation(DOMAIN, localedir=str(LOCALE_DIR), languages=[lang])
        except FileNotFoundError:
            _translations[lang] = gettext.NullTranslations()
    return _translations[lang]


def available_languages() -> list[tuple[str, str]]:
    """Languages discovered under ``locale/``, as ``(code, native_name)``.

    Scans for compiled ``LC_MESSAGES/soundblaster_g8.mo`` files - a language
    is available if (and only if) it has one, regardless of what's hardcoded
    here.
    """
    codes = sorted(
        mo_path.parent.parent.name
        for mo_path in LOCALE_DIR.glob("*/LC_MESSAGES/" + DOMAIN + ".mo")
    )
    if not codes:
        return [(DEFAULT_LANGUAGE, "English")]
    return [(code, _get_translation(code).gettext("language.native_name")) for code in codes]


def get_language() -> str:
    return _current_language


def set_language(lang: str) -> None:
    global _current_language
    _current_language = lang
    _save_language(lang)
    for listener in list(_listeners):
        try:
            listener(lang)
        except Exception as exc:  # pragma: no cover - defensive, mirrors controller.py listener pattern
            print(f"[i18n] Listener error: {exc}")


def add_listener(callback: Callable[[str], None]) -> None:
    _listeners.append(callback)


def load_saved_language() -> str:
    """Reads the persisted language preference, falling back to the default.

    Called once before the UI is built so the very first strings rendered
    already reflect the saved preference (no flash of the default language).
    """
    global _current_language
    lang = DEFAULT_LANGUAGE
    try:
        data = json.loads(_settings_path().read_text(encoding="utf-8"))
        saved = data.get("language")
        if isinstance(saved, str) and saved:
            lang = saved
    except (OSError, ValueError):
        pass
    _current_language = lang
    return lang


def _save_language(lang: str) -> None:
    path = _settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"language": lang}), encoding="utf-8")
    except OSError:
        pass


def _(message: str) -> str:
    """Translate ``message`` (an English string) to the current language."""
    return _get_translation(_current_language).gettext(message)


def sound_mode_label(slug: str, fallback_label: str) -> str:
    """Translated display label for a sound-mode slug.

    Falls back to the data-file label unchanged for slugs with no override
    (the ~47 vendor game-title presets, already language-neutral).
    """
    if slug not in _SOUND_MODE_SLUGS:
        return fallback_label
    return _(f"sound_mode.{slug}")


def _prefixed_label(prefix: str, slug: str, fallback_label: str) -> str:
    """Translated label for a ``<prefix>.<slug>`` catalog key.

    An untranslated key comes back as the msgid itself, in which case the
    data-file label is used instead.
    """
    msgid = f"{prefix}.{slug}"
    translated = _(msgid)
    return fallback_label if translated == msgid else translated


def crystalvoice_preset_label(slug: str, fallback_label: str) -> str:
    """Translated display label for a Voice Morph / Microphone Equalizer slug.

    Unlike :func:`sound_mode_label`, every CrystalVoice preset has a catalog
    entry (they all come from the French Creative app), so there's no slug
    whitelist to keep in sync.
    """
    return _prefixed_label("crystalvoice_preset", slug, fallback_label)


def decoder_mode_label(slug: str, fallback_label: str) -> str:
    """Translated display label for a decoder (DRC) mode slug."""
    return _prefixed_label("decoder_mode", slug, fallback_label)
