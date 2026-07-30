"""
Module de contrôle pour la carte Sound Blaster G8.

Contient la logique métier et fait abstraction du driver. Toutes les méthodes
``set_*`` retournent un booléen indiquant si le matériel a bien appliqué la
commande : la GUI peut ainsi refuser de basculer un interrupteur quand la
carte n'a pas répondu.
"""

from typing import Callable, Optional

from .driver import SoundBlasterG8Driver, get_driver

#: Fonctions dont la trame USB a été identifiée et validée sur le matériel.
SUPPORTED_FEATURES = frozenset({"scout_mode"})


class SoundBlasterController:
    """Contrôleur principal pour la carte Sound Blaster G8.

    Sert d'intermédiaire entre l'interface GUI et le driver matériel.
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
            "command_failed": [],
        }

    # ------------------------------------------------------------------
    # Connectivité
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Établit la connexion au matériel puis charge l'état connu."""
        connected = self._driver.connect()
        if connected:
            self._load_current_state()
        return connected

    def disconnect(self) -> None:
        """Déconnecte du matériel."""
        self._driver.disconnect()

    def is_connected(self) -> bool:
        """Vérifie la connexion au matériel réel."""
        return self._driver.is_connected()

    def is_simulated(self) -> bool:
        """``True`` si aucun matériel n'a été détecté."""
        return self._driver.is_simulated()

    def get_debug_info(self) -> dict:
        return self._driver.get_debug_info()

    @staticmethod
    def is_feature_supported(name: str) -> bool:
        """Indique si la trame USB de cette fonction est connue.

        Les fonctions non supportées n'ont pas encore été capturées : les
        activer n'aurait aucun effet sur la carte.
        """
        return name in SUPPORTED_FEATURES

    def _load_current_state(self) -> None:
        """Charge l'état connu depuis le driver (sans écraser par des None)."""
        for name, getter in (
            ("_direct_mode", self._driver.get_direct_mode),
            ("_scout_mode", self._driver.get_scout_mode),
            ("_crystalvoice", self._driver.get_crystalvoice),
        ):
            try:
                value = getter()
            except Exception as exc:
                print(f"[SoundBlasterController] Lecture de {name} impossible: {exc}")
                continue
            if value is not None:
                setattr(self, name, bool(value))

        try:
            bands = self._driver.eq_get_all_bands()
        except Exception as exc:
            print(f"[SoundBlasterController] Lecture de l'EQ impossible: {exc}")
            bands = None
        if bands:
            self._eq_bands = list(bands)

        print("[SoundBlasterController] État initial chargé")

    # ------------------------------------------------------------------
    # Scout Mode (supporté)
    # ------------------------------------------------------------------

    def set_scout_mode(self, enabled: bool) -> bool:
        """Active/désactive le mode Scout.

        Returns:
            ``True`` si la carte a confirmé la commande.
        """
        ok = bool(self._driver.set_scout_mode(enabled))
        if ok:
            self._scout_mode = enabled
            self._notify("scout_mode_changed", enabled)
        else:
            self._notify("command_failed", "scout_mode", enabled)
        return ok

    def get_scout_mode(self) -> bool:
        """Retourne l'état connu du mode Scout."""
        state = self._driver.get_scout_mode()
        if state is not None:
            self._scout_mode = state
        return self._scout_mode

    # ------------------------------------------------------------------
    # Fonctions non encore reversées
    # ------------------------------------------------------------------

    def set_direct_mode(self, enabled: bool) -> bool:
        ok = bool(self._driver.set_direct_mode(enabled))
        if ok:
            self._direct_mode = enabled
            self._notify("direct_mode_changed", enabled)
        else:
            self._notify("command_failed", "direct_mode", enabled)
        return ok

    def get_direct_mode(self) -> bool:
        return self._direct_mode

    def set_crystalvoice(self, enabled: bool) -> bool:
        ok = bool(self._driver.set_crystalvoice(enabled))
        if ok:
            self._crystalvoice = enabled
            self._notify("crystalvoice_changed", enabled)
        else:
            self._notify("command_failed", "crystalvoice", enabled)
        return ok

    def get_crystalvoice(self) -> bool:
        return self._crystalvoice

    # ------------------------------------------------------------------
    # EQ 10 bandes (état local uniquement pour l'instant)
    # ------------------------------------------------------------------

    def set_eq_band(self, index: int, value: float) -> bool:
        """Règle une bande d'égaliseur avec validation.

        Args:
            index: Index de la bande (0-9)
            value: Valeur en dB (-12 à +12)
        """
        if not 0 <= index < self.NUM_BANDS:
            raise ValueError(f"Index de bande invalide: {index}")

        clamped = max(self.MIN_EQ_VALUE, min(self.MAX_EQ_VALUE, value))
        ok = bool(self._driver.eq_set_band(index, clamped))
        # L'état local suit le curseur même si le matériel ne l'applique pas
        # encore, afin de garder une GUI cohérente.
        self._eq_bands[index] = clamped
        self._notify("eq_band_changed", index, clamped)
        if not ok:
            self._notify("command_failed", "eq_band", index)
        return ok

    def get_eq_band(self, index: int) -> float:
        if not 0 <= index < self.NUM_BANDS:
            raise ValueError(f"Index de bande invalide: {index}")
        return self._eq_bands[index]

    def get_eq_all_bands(self) -> list[float]:
        return self._eq_bands.copy()

    def load_preset(self, preset_name: str) -> bool:
        """Charge un preset prédéfini.

        Presets disponibles: flat, bass_boost, vocal, gaming, movie.
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

        all_ok = True
        for i, value in enumerate(presets[preset_name]):
            self._eq_bands[i] = value
            if not self._driver.eq_set_band(i, value):
                all_ok = False
        self._notify("eq_all_bands_changed", presets[preset_name])
        return all_ok

    def save_preset(self, preset_name: str) -> bool:
        """Sauvegarde l'état actuel de l'égaliseur sur la carte."""
        return bool(self._driver.eq_save_preset(preset_name))

    # ------------------------------------------------------------------
    # Listeners / événements
    # ------------------------------------------------------------------

    def add_listener(self, event: str, callback: Callable) -> None:
        if event in self._listeners:
            self._listeners[event].append(callback)

    def remove_listener(self, event: str, callback: Callable) -> None:
        if event in self._listeners and callback in self._listeners[event]:
            self._listeners[event].remove(callback)

    def _notify(self, event: str, *args) -> None:
        for callback in self._listeners.get(event, []):
            try:
                callback(*args)
            except Exception as exc:
                print(f"[SoundBlasterController] Erreur dans le listener {event}: {exc}")


# Singleton controller
_controller_instance: Optional[SoundBlasterController] = None


def get_controller() -> SoundBlasterController:
    """Retourne l'instance singleton du contrôleur."""
    global _controller_instance
    if _controller_instance is None:
        _controller_instance = SoundBlasterController()
    return _controller_instance
