"""
Sélection du backend HID, unifiée macOS / Linux / Windows.

C'est le **seul** module du projet qui dépend de la plateforme : le driver ne
doit importer ni ``hid`` ni ``hidraw`` directement.

Sur Linux, ``pip install hidapi`` installe deux modules Python :

* ``hid``    : backend **libusb** (celui fourni par les *wheels* binaires ;
  il détache le driver noyau ``usbhid`` le temps de l'accès et **ne renseigne
  pas** ``usage_page`` dans ``hid_enumerate``).
* ``hidraw`` : backend **hidraw** (pas de détachement du driver noyau,
  ``usage_page`` lu depuis le report descriptor exposé par sysfs). Il n'est
  présent que si hidapi a été compilé avec ``HIDAPI_WITH_HIDRAW=1``.

Les deux modules exposent la même API Python (``hidraw.pyx`` est une copie de
``hid.pyx`` dans cython-hidapi), d'où la possibilité de les intervertir.

Ordre de préférence :

* Linux   : ``hidraw`` puis ``hid`` (libusb).
* macOS   : ``hid`` (IOKit, seul disponible).
* Windows : ``hid`` (setupapi, seul disponible).

Le backend retenu est journalisé au premier appel : c'est l'information la
plus utile en cas de comportement divergent entre deux machines Linux.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass
from typing import Any, Iterable, Optional

_SYSTEM = platform.system()


@dataclass(frozen=True)
class BackendInfo:
    """Résultat de la sélection de backend."""

    module: Any
    name: str
    provides_usage_page: bool

    def __str__(self) -> str:  # pragma: no cover - affichage debug
        usage = "oui" if self.provides_usage_page else "non"
        return f"{self.name} (usage_page énuméré : {usage})"


_backend_cache: Optional[BackendInfo] = None
_logged = False


def _log(message: str) -> None:
    print(f"[hidbackend] {message}")


def _module_ok(mod: Any) -> bool:
    return mod is not None and hasattr(mod, "enumerate") and hasattr(mod, "device")


def _select() -> BackendInfo:
    if _SYSTEM == "Linux":
        try:
            import hidraw  # type: ignore
        except ImportError:
            hidraw = None  # type: ignore
        try:
            import hid  # type: ignore
        except ImportError:
            hid = None  # type: ignore

        # hidraw d'abord : il renseigne usage_page et ne détache pas le driver
        # noyau, ce qui évite de couper les périphériques audio/média de la
        # carte pendant qu'on parle au canal de contrôle.
        if _module_ok(hidraw):
            return BackendInfo(module=hidraw, name="hidraw", provides_usage_page=True)
        if _module_ok(hid):
            return BackendInfo(module=hid, name="libusb", provides_usage_page=False)
        raise ImportError(
            "Aucun backend HID disponible. Installez hidapi "
            "('pip install hidapi') ; pour obtenir le backend hidraw : "
            "'HIDAPI_WITH_HIDRAW=1 pip install --no-binary :all: hidapi'."
        )

    try:
        import hid  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "Module 'hid' (hidapi) introuvable : 'pip install hidapi'."
        ) from exc

    return BackendInfo(
        module=hid,
        name="iokit" if _SYSTEM == "Darwin" else "windows",
        provides_usage_page=True,
    )


def get_backend() -> BackendInfo:
    """Retourne le backend HID à utiliser, mis en cache au premier appel."""
    global _backend_cache, _logged
    if _backend_cache is None:
        _backend_cache = _select()
    if not _logged:
        _logged = True
        _log(f"plateforme {_SYSTEM}, backend retenu : {_backend_cache}")
    return _backend_cache


def is_available() -> bool:
    """``True`` si un backend HID utilisable est installé."""
    try:
        get_backend()
    except ImportError as exc:
        _log(f"aucun backend HID : {exc}")
        return False
    return True


def backend_name() -> str:
    """Nom du backend retenu : ``hidraw`` / ``libusb`` / ``iokit`` / ``windows``."""
    try:
        return get_backend().name
    except ImportError:
        return "aucun"


def provides_usage_page() -> bool:
    """``False`` avec libusb : ``hid_enumerate`` n'y renseigne pas ``usage_page``.

    Le driver s'en sert pour savoir que la sélection d'interface doit se replier
    sur ``interface_number`` sans que ce soit considéré comme anormal.
    """
    try:
        return get_backend().provides_usage_page
    except ImportError:
        return False


def enumerate(vendor_id: int = 0, product_id: int = 0) -> list[dict]:
    """``hid_enumerate`` du backend retenu, sous forme de liste de dicts."""
    entries: Iterable[dict] = get_backend().module.enumerate(vendor_id, product_id)
    return list(entries)


def open_path(path: bytes) -> Any:
    """Ouvre un device HID par son ``path`` et retourne le handle du backend."""
    device = get_backend().module.device()
    device.open_path(path)
    return device


def reset_cache() -> None:
    """Efface le cache (utile pour les tests)."""
    global _backend_cache, _logged
    _backend_cache = None
    _logged = False
