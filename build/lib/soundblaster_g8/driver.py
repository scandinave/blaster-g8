"""
Driver mock pour la carte son Creative Sound Blaster G8.
Cette classe simule les appels vers le matériel en utilisant print().
"""

from typing import Optional


class SoundBlasterG8Driver:
    """Mock driver pour la carte Sound Blaster G8."""

    def __init__(self):
        self._connected = False
        print("[SoundBlasterG8Driver] Initialisation du driver")

    def connect(self) -> bool:
        """Établit une connexion avec la carte son."""
        print("[SoundBlasterG8Driver] Tentative de connexion à la carte Sound Blaster G8...")
        self._connected = True
        print("[SoundBlasterG8Driver] Connexion établie")
        return self._connected

    def disconnect(self):
        """Détache la carte son."""
        if self._connected:
            print("[SoundBlasterG8Driver] Déconnexion de la carte Sound Blaster G8")
            self._connected = False
        else:
            print("[SoundBlasterG8Driver] Carte déjà déconnectée")

    def is_connected(self) -> bool:
        """Vérifie si la carte est connectée."""
        return self._connected

    # Direct Mode
    def set_direct_mode(self, enabled: bool) -> None:
        """Active ou désactive le mode direct (pas de traitement du signal)."""
        if not self._connected:
            print("[SoundBlasterG8Driver] ERREUR: Carte non connectée pour set_direct_mode")
            return
        mode_str = "activé" if enabled else "désactivé"
        print(f"[SoundBlasterG8Driver] Mode Direct {mode_str}")

    def get_direct_mode(self) -> bool:
        """Retourne l'état du mode direct."""
        if not self._connected:
            print("[SoundBlasterG8Driver] ERREUR: Carte non connectée pour get_direct_mode")
            return False
        print("[SoundBlasterG8Driver] Lecture de l'état du mode Direct")
        return False  # Valeur par défaut

    # Scout Mode
    def set_scout_mode(self, enabled: bool) -> None:
        """Active ou désactive le mode Scout (détection de pas/bruits)."""
        if not self._connected:
            print("[SoundBlasterG8Driver] ERREUR: Carte non connectée pour set_scout_mode")
            return
        mode_str = "activé" if enabled else "désactivé"
        print(f"[SoundBlasterG8Driver] Mode Scout {mode_str}")

    def get_scout_mode(self) -> bool:
        """Retourne l'état du mode Scout."""
        if not self._connected:
            print("[SoundBlasterG8Driver] ERREUR: Carte non connectée pour get_scout_mode")
            return False
        print("[SoundBlasterG8Driver] Lecture de l'état du mode Scout")
        return False  # Valeur par défaut

    # CrystalVoice (Voix)
    def set_crystalvoice(self, enabled: bool) -> None:
        """Active ou désactive CrystalVoice (traitement vocal)."""
        if not self._connected:
            print("[SoundBlasterG8Driver] ERREUR: Carte non connectée pour set_crystalvoice")
            return
        mode_str = "activé" if enabled else "désactivé"
        print(f"[SoundBlasterG8Driver] CrystalVoice {mode_str}")

    def get_crystalvoice(self) -> bool:
        """Retourne l'état de CrystalVoice."""
        if not self._connected:
            print("[SoundBlasterG8Driver] ERREUR: Carte non connectée pour get_crystalvoice")
            return False
        print("[SoundBlasterG8Driver] Lecture de l'état de CrystalVoice")
        return False  # Valeur par défaut

    # EQ à 10 bandes
    def eq_get_all_bands(self) -> list[float]:
        """Retourne les niveaux des 10 bandes d'égaliseur."""
        if not self._connected:
            print("[SoundBlasterG8Driver] ERREUR: Carte non connectée pour eq_get_all_bands")
            return [0.0] * 10
        print("[SoundBlasterG8Driver] Lecture des paramètres d'égaliseur (10 bandes)")
        return [0.0] * 10  # Valeurs par défaut à 0dB

    def eq_set_band(self, index: int, value: float) -> None:
        """Règle le niveau d'une bande spécifique."""
        if not self._connected:
            print(f"[SoundBlasterG8Driver] ERREUR: Carte non connectée pour eq_set_band ({index})")
            return
        if not 0 <= index < 10:
            print(f"[SoundBlasterG8Driver] ERREUR: Index hors limites {index}")
            return
        print(f"[SoundBlasterG8Driver] Égaliseur - Bande {index}: {value:.2f} dB")

    def eq_load_preset(self, preset_name: str) -> None:
        """Charge unpreset d'égaliseur."""
        if not self._connected:
            print(f"[SoundBlasterG8Driver] ERREUR: Carte non connectée pour eq_load_preset ({preset_name})")
            return
        print(f"[SoundBlasterG8Driver] Chargement du preset EQ: {preset_name}")

    def eq_save_preset(self, preset_name: str) -> None:
        """Sauvegarde le preset d'égaliseur actuel."""
        if not self._connected:
            print(f"[SoundBlasterG8Driver] ERREUR: Carte non connectée pour eq_save_preset ({preset_name})")
            return
        print(f"[SoundBlasterG8Driver] Sauvegarde du preset EQ: {preset_name}")


# Singleton instance
_driver_instance: Optional[SoundBlasterG8Driver] = None


def get_driver() -> SoundBlasterG8Driver:
    """Retourne l'instance singleton du driver."""
    global _driver_instance
    if _driver_instance is None:
        _driver_instance = SoundBlasterG8Driver()
    return _driver_instance