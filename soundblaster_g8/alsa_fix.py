"""
Correctif ALSA pour le microphone de la Sound Blaster G8 sous Linux.

Le pilote noyau ``snd-usb-audio`` initialise le contrôle ALSA
« PCM Capture Source » sur ``Line In`` au lieu de ``External Mic`` : le
microphone ne capte donc rien tant qu'on n'a pas changé la source manuellement
(alsamixer/pavucontrol), à chaque redémarrage de la carte.

Ce module réapplique le correctif au démarrage de l'application. Il existe
aussi un correctif système indépendant (règle udev + script, dossier
``alsa-fix/`` à la racine du dépôt) qui s'applique même sans lancer l'app :
les deux mécanismes sont redondants par sécurité.

Découverte de la carte via ``/proc/asound/card*/usbid`` (fourni par le noyau,
jamais localisé) plutôt qu'en parsant la sortie de ``aplay -l``, qui est
localisée (``carte 1 : ...`` en français au lieu de ``card 1: ...``) et rend le
matching par nom de carte non fiable.

Ciblage du contrôle par nom (``amixer sset 'PCM Capture Source' ...``) plutôt
que par ``numid``, qui peut se renuméroter d'une version de pilote/noyau à
l'autre.
"""

from __future__ import annotations

import glob
import platform
import subprocess
from typing import Optional

CAPTURE_SOURCE_CONTROL = "PCM Capture Source"
CAPTURE_SOURCE_TARGET = "External Mic"

AMIXER_TIMEOUT_S = 3.0


def _log(message: str) -> None:
    print(f"[ALSAFix] {message}")


def find_card_index(vendor_id: int, product_id: int) -> Optional[int]:
    """Trouve l'index de carte ALSA correspondant au VID:PID donné.

    Lit ``/proc/asound/card*/usbid`` (ex. ``041e:329b``) : contrairement à
    ``aplay -l``, ce fichier n'est jamais localisé.
    """
    target = f"{vendor_id:04x}:{product_id:04x}"
    for usbid_path in sorted(glob.glob("/proc/asound/card*/usbid")):
        try:
            with open(usbid_path, "r", encoding="ascii") as f:
                content = f.read().strip()
        except OSError:
            continue
        if content == target:
            # .../card<N>/usbid
            digits = usbid_path.split("/card", 1)[1].split("/", 1)[0]
            try:
                return int(digits)
            except ValueError:
                continue
    return None


def ensure_microphone_source(vendor_id: int, product_id: int) -> bool:
    """Sélectionne ``External Mic`` comme source de capture ALSA.

    Ne fait rien (et ne lève jamais) hors Linux, si la carte ALSA n'est pas
    trouvée, si ``amixer`` est absent, ou si la commande échoue : ce correctif
    est un « best effort » qui ne doit jamais empêcher l'application de
    démarrer.
    """
    if platform.system() != "Linux":
        return False

    card_index = find_card_index(vendor_id, product_id)
    if card_index is None:
        _log("carte ALSA introuvable (/proc/asound/card*/usbid) : correctif ignoré")
        return False

    try:
        result = subprocess.run(
            [
                "amixer",
                "-c",
                str(card_index),
                "-q",
                "sset",
                CAPTURE_SOURCE_CONTROL,
                CAPTURE_SOURCE_TARGET,
            ],
            capture_output=True,
            text=True,
            timeout=AMIXER_TIMEOUT_S,
        )
    except FileNotFoundError:
        _log("commande 'amixer' introuvable (paquet alsa-utils manquant) : correctif ignoré")
        return False
    except subprocess.TimeoutExpired:
        _log(f"'amixer' n'a pas répondu (carte {card_index}) : correctif ignoré")
        return False
    except OSError as exc:
        _log(f"échec de l'appel à 'amixer' (carte {card_index}): {exc}")
        return False

    if result.returncode != 0:
        _log(
            f"échec de la sélection de source de capture (carte {card_index}): "
            f"{result.stderr.strip() or result.returncode}"
        )
        return False

    _log(f"source de capture réglée sur '{CAPTURE_SOURCE_TARGET}' (carte {card_index})")
    return True
