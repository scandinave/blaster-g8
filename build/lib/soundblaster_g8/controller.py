"""
Module de contrôle pour la carte Sound Blaster G8.
Contient la logique métier et fait abstraction du driver.
"""

from typing import Callable, Optional

from .driver import SoundBlasterG8Driver, get_driver


class SoundBlasterController:
    """Contrôleur principal pour la carte Sound Blaster G8.

    Cette classe encapsule la logique métier et sert d'intermédiaire entre
    l'interface GUI et le driver matériel.
    """

    MIN_EQ_VALUE = -12.0  # Plage EQ en dB
    MAX_EQ_VALUE = 12.0
    NUM_BANDS = 10

    def __init__(self, driver: Optional[SoundBlasterG8Driver] = None):
        """Initialise le contrôleur.

        Args:
            driver: Optionnel - Un driver spécifique pour les tests unitaires.
        """
        self._driver = driver if driver else get_driver()
        self._direct_mode = False
        self._scout_mode = False
        self._crystalvoice = False
        self._eq_bands: list[float] = [0.0] * self.NUM_BANDS

        # Listeners pour les événements (pour notification à la GUI)
        self._listeners: dict[str, list[Callable]] = {
            "direct_mode_changed": [],
            "scout_mode_changed": [],
            "crystalvoice_changed": [],
            "eq_band_changed": [],
            "eq_all_bands_changed": [],
        }

        # Initialisation de la connexion au driver
        if self._driver.is_connected():
            self._load_current_state()

    def _load_current_state(self):
        """Charge l'état actuel depuis le driver."""
        try:
            self._direct_mode = self._driver.get_direct_mode()
            self._scout_mode = self._driver.get_scout_mode()
            self._crystalvoice = self._driver.get_crystalvoice()
            self._eq_bands = self._driver.eq_get_all_bands()
            print("[SoundBlasterController] État chargé depuis le driver")
        except Exception as e:
            print(f"[SoundBlasterController] Erreur lors du chargement de l'état: {e}")

    # Connectivité
    def connect(self) -> bool:
        """Établit la connexion au matériel."""
        return self._driver.connect()

    def disconnect(self):
        """Déconnecte du matériel."""
        self._driver.disconnect()

    def is_connected(self) -> bool:
        """Vérifie la connexion."""
        return self._driver.is_connected()

    # Direct Mode
    def set_direct_mode(self, enabled: bool) -> None:
        """Active/désactive le mode direct et notifie les listeners."""
        if self._direct_mode != enabled:
            self._direct_mode = enabled
            if self._driver.is_connected():
                self._driver.set_direct_mode(enabled)
            self._notify("direct_mode_changed", enabled)

    def get_direct_mode(self) -> bool:
        """Retourne l'état du mode direct."""
        return self._direct_mode

    # Scout Mode
    def set_scout_mode(self, enabled: bool) -> None:
        """Active/désactive le mode Scout et notifie les listeners."""
        if self._scout_mode != enabled:
            self._scout_mode = enabled
            if self._driver.is_connected():
                self._driver.set_scout_mode(enabled)
            self._notify("scout_mode_changed", enabled)

    def get_scout_mode(self) -> bool:
        """Retourne l'état du mode Scout."""
        return self._scout_mode

    # CrystalVoice
    def set_crystalvoice(self, enabled: bool) -> None:
        """Active/désactive CrystalVoice et notifie les listeners."""
        if self._crystalvoice != enabled:
            self._crystalvoice = enabled
            if self._driver.is_connected():
                self._driver.set_crystalvoice(enabled)
            self._notify("crystalvoice_changed", enabled)

    def get_crystalvoice(self) -> bool:
        """Retourne l'état de CrystalVoice."""
        return self._crystalvoice

    # EQ Bandes (10 bandes)
    def set_eq_band(self, index: int, value: float) -> None:
        """Règle une bande d'égaliseur avec validation.

        Args:
            index: Index de la bande (0-9)
            value: Valeur en dB (-12 à +12)
        """
        if not 0 <= index < self.NUM_BANDS:
            raise ValueError(f"Index de bande invalide: {index}")
        clamped_value = max(self.MIN_EQ_VALUE, min(self.MAX_EQ_VALUE, value))
        if self._eq_bands[index] != clamped_value:
            self._eq_bands[index] = clamped_value
            if self._driver.is_connected():
                self._driver.eq_set_band(index, clamped_value)
            self._notify("eq_band_changed", index, clamped_value)

    def get_eq_band(self, index: int) -> float:
        """Retourne la valeur d'une bande spécifique."""
        if not 0 <= index < self.NUM_BANDS:
            raise ValueError(f"Index de bande invalide: {index}")
        return self._eq_bands[index]

    def get_eq_all_bands(self) -> list[float]:
        """Retourne toutes les bandes d'égaliseur."""
        return self._eq_bands.copy()

    def load_preset(self, preset_name: str) -> None:
        """Charge un preset prédéfini.

        Presets disponibles:
            - flat: Toutes bandes à 0 dB
            - bass_boost: Renforcement des basses
            - vocal: Optimisé pour la voix
            - gaming: Optimisé pour le gaming
            - movie: Cinématique
        """
        presets = {
            "flat": [0.0] * self.NUM_BANDS,
            "bass_boost": [+4.0, +3.0, +2.0, +1.0, 0.0, 0.0, -1.0, -1.0, -2.0, -3.0],
            "vocal": [0.0, 0.0, 0.0, +2.0, +3.0, +2.0, 0.0, -1.0, -2.0, -3.0],
            "gaming": [+2.0, +3.0, +4.0, +3.0, +2.0, 0.0, -1.0, -2.0, -2.0, -3.0],
            "movie": [+3.0, +2.0, +1.0, 0.0, 0.0, 0.0, +1.0, +2.0, +3.0, +4.0],
        }

        if preset_name not in presets:
            raise ValueError(f"Preset inconnu: {preset_name}")

        for i, value in enumerate(presets[preset_name]):
            self._eq_bands[i] = value
            if self._driver.is_connected():
                self._driver.eq_set_band(i, value)
        self._notify("eq_all_bands_changed", presets[preset_name])

    def save_preset(self, preset_name: str) -> None:
        """Sauvegarde l'état actuel de l'égaliseur.

        Args:
            preset_name: Nom du preset à sauvegarder
        """
        if self._driver.is_connected():
            self._driver.eq_save_preset(preset_name)
        print(f"[SoundBlasterController] Preset '{preset_name}' sauvegardé")

    # Listeners/Events
    def add_listener(self, event: str, callback: Callable):
        """Ajoute un listener pour un événement."""
        if event in self._listeners:
            self._listeners[event].append(callback)

    def remove_listener(self, event: str, callback: Callable):
        """Retire un listener."""
        if event in self._listeners and callback in self._listeners[event]:
            self._listeners[event].remove(callback)

    def _notify(self, event: str, *args):
        """Notifie tous les listeners d'un événement."""
        for callback in self._listeners.get(event, []):
            try:
                callback(*args)
            except Exception as e:
                print(f"[SoundBlasterController] Erreur dans le listener {event}: {e}")


# Singleton controller
_controller_instance: Optional[SoundBlasterController] = None


def get_controller() -> SoundBlasterController:
    """Retourne l'instance singleton du contrôleur."""
    global _controller_instance
    if _controller_instance is None:
        _controller_instance = SoundBlasterController()
    return _controller_instance