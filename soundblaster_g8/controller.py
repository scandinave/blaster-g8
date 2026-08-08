"""
Control module for the Sound Blaster G8 card.

Contains the business logic and abstracts away the driver. Every ``set_*``
method returns a boolean indicating whether the hardware actually applied
the command: the GUI can thus refuse to flip a switch when the card didn't
respond.
"""

from typing import Callable, Optional

from . import alsa_fix, protocol
from .crystalvoice_presets import (
    DEFAULT_MIC_EQ,
    DEFAULT_VOICE_MORPH,
    MIC_EQ_PRESETS,
    VOICE_MORPH_PRESETS,
)
from .driver import PRODUCT_ID, VENDOR_ID, SoundBlasterG8Driver, get_driver
from .sound_modes import DEFAULT_SOUND_MODE, SOUND_MODES

#: Features whose USB frame has been identified and validated on hardware.
SUPPORTED_FEATURES = frozenset({"scout_mode", "direct_mode", "sound_mode", "eq", "crystalvoice"})

#: "Tilt" weights for the Bass/Treble sliders (bands 0x0b..0x14, in that
#: order). These two sliders have no dedicated parameter on the card: in
#: the ``Equalizer-manual.pcapng`` capture, moving them rewrites the 10
#: existing bands with a curve decreasing from one end of the spectrum. The
#: weights below are the deltas measured in that capture, normalized so a
#: slider at +12 dB reproduces the captured gesture: this is an
#: **approximation** of Creative's real algorithm, not a value guaranteed
#: to be identical.
BASS_TILT_WEIGHTS = (0.27061, 0.28224, 0.20667, 0.10533, 0.044, 0.012, 0.0, 0.0, 0.0, 0.0)
TREBLE_TILT_WEIGHTS = (0.0, 0.0, 0.0, 0.00773, 0.02591, 0.04182, 0.09182, 0.19955, 0.34167, 0.35637)


class SoundBlasterController:
    """Main controller for the Sound Blaster G8 card.

    Acts as an intermediary between the GUI and the hardware driver.
    """

    MIN_EQ_VALUE = -12.0  # EQ range in dB
    MAX_EQ_VALUE = 12.0
    NUM_BANDS = 10

    def __init__(self, driver: Optional[SoundBlasterG8Driver] = None):
        """Initializes the controller.

        Args:
            driver: Optional - a specific driver for unit tests.
        """
        self._driver = driver if driver else get_driver()
        self._direct_mode = False
        self._scout_mode = False
        self._cv_noise_reduction = False
        self._cv_noise_reduction_level = 0.0
        self._cv_echo_cancellation = False
        self._cv_smart_volume = False
        self._cv_voice_morph = False
        self._cv_voice_morph_preset: str = DEFAULT_VOICE_MORPH
        self._cv_mic_equalizer = False
        self._cv_mic_equalizer_preset: str = DEFAULT_MIC_EQ
        self._eq_bands: list[float] = [0.0] * self.NUM_BANDS
        self._eq_preamp: float = 0.0
        self._eq_enabled: bool = False
        # Persistent position of the Bass/Treble sliders (see set_eq_bass/
        # set_eq_treble): unlike bands, these aren't card parameters but a
        # UI position from which a delta is derived on each change.
        self._eq_bass: float = 0.0
        self._eq_treble: float = 0.0
        self._sound_mode: str = DEFAULT_SOUND_MODE

        # Listeners for events (to notify the GUI)
        self._listeners: dict[str, list[Callable]] = {
            "direct_mode_changed": [],
            "scout_mode_changed": [],
            "crystalvoice_noise_reduction_changed": [],
            "crystalvoice_noise_reduction_level_changed": [],
            "crystalvoice_echo_cancellation_changed": [],
            "crystalvoice_smart_volume_changed": [],
            "crystalvoice_voice_morph_changed": [],
            "crystalvoice_voice_morph_preset_changed": [],
            "crystalvoice_mic_equalizer_changed": [],
            "crystalvoice_mic_equalizer_preset_changed": [],
            "eq_band_changed": [],
            "eq_all_bands_changed": [],
            "eq_preamp_changed": [],
            "eq_enabled_changed": [],
            "eq_bass_changed": [],
            "eq_treble_changed": [],
            "sound_mode_changed": [],
            "command_failed": [],
            # (bool): True when the card is re-enumerating (Direct Mode
            # toggle), False when the reconnection is complete.
            "reconnecting": [],
        }

        # The driver signals reconnections: relay them as-is.
        self._driver.on_reconnecting = lambda active: self._notify("reconnecting", active)

    # ------------------------------------------------------------------
    # Connectivity
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Establishes the hardware connection then loads the known state.

        Also re-applies the ALSA fix (mic capture source, see
        :mod:`soundblaster_g8.alsa_fix`): this bug is independent of the
        HID control channel, so it's handled even if the HID connection
        fails.
        """
        alsa_fix.ensure_microphone_source(VENDOR_ID, PRODUCT_ID)
        connected = self._driver.connect()
        if connected:
            self._load_current_state()
        return connected

    def disconnect(self) -> None:
        """Disconnects from the hardware."""
        self._driver.disconnect()

    def is_connected(self) -> bool:
        """Checks the connection to the real hardware."""
        return self._driver.is_connected()

    def is_simulated(self) -> bool:
        """``True`` if no hardware was detected."""
        return self._driver.is_simulated()

    def get_debug_info(self) -> dict:
        return self._driver.get_debug_info()

    @staticmethod
    def is_feature_supported(name: str) -> bool:
        """Indicates whether this feature's USB frame is known.

        Unsupported features haven't been captured yet: enabling them
        would have no effect on the card.
        """
        return name in SUPPORTED_FEATURES

    def _load_current_state(self) -> None:
        """Loads the known state from the driver (without overwriting with None)."""
        for name, getter in (
            ("_direct_mode", self._driver.get_direct_mode),
            ("_scout_mode", self._driver.get_scout_mode),
            ("_cv_noise_reduction", self._driver.get_crystalvoice_noise_reduction),
            ("_cv_echo_cancellation", self._driver.get_crystalvoice_echo_cancellation),
            ("_cv_smart_volume", self._driver.get_crystalvoice_smart_volume),
            ("_cv_voice_morph", self._driver.get_crystalvoice_voice_morph),
            ("_cv_mic_equalizer", self._driver.get_crystalvoice_mic_equalizer),
        ):
            try:
                value = getter()
            except Exception as exc:
                print(f"[SoundBlasterController] Unable to read {name}: {exc}")
                continue
            if value is not None:
                setattr(self, name, bool(value))

        try:
            level = self._driver.get_crystalvoice_noise_reduction_level()
        except Exception as exc:
            print(f"[SoundBlasterController] Unable to read _cv_noise_reduction_level: {exc}")
            level = None
        if level is not None:
            self._cv_noise_reduction_level = level

        try:
            bands = self._driver.eq_get_all_bands()
        except Exception as exc:
            print(f"[SoundBlasterController] Unable to read the EQ: {exc}")
            bands = None
        if bands:
            self._eq_bands = list(bands)

        try:
            preamp = self._driver.eq_get_preamp()
        except Exception as exc:
            print(f"[SoundBlasterController] Unable to read the Preamp: {exc}")
            preamp = None
        if preamp is not None:
            self._eq_preamp = preamp

        print("[SoundBlasterController] Initial state loaded")

    # ------------------------------------------------------------------
    # Scout Mode (supported)
    # ------------------------------------------------------------------

    def set_scout_mode(self, enabled: bool) -> bool:
        """Enables/disables Scout Mode.

        Returns:
            ``True`` if the card confirmed the command.
        """
        ok = bool(self._driver.set_scout_mode(enabled))
        if ok:
            self._scout_mode = enabled
            self._notify("scout_mode_changed", enabled)
        else:
            self._notify("command_failed", "scout_mode", enabled)
        return ok

    def get_scout_mode(self) -> bool:
        """Returns Scout Mode's known state."""
        state = self._driver.get_scout_mode()
        if state is not None:
            self._scout_mode = state
        return self._scout_mode

    # ------------------------------------------------------------------
    # Direct Mode (supported)
    # ------------------------------------------------------------------

    def set_direct_mode(self, enabled: bool) -> bool:
        """Enables/disables Direct Mode.

        The toggle triggers a USB reset of the card: the call can take
        several seconds (the ``reconnecting`` event brackets the wait) and
        must therefore not be made from the GUI thread.

        Returns:
            ``True`` if the card acknowledged the command **and** was
            reopened.
        """
        ok = bool(self._driver.set_direct_mode(enabled))
        if not ok:
            self._notify("command_failed", "direct_mode", enabled)
            return False

        self._direct_mode = enabled
        # The USB reset may have reset other settings to their default
        # value: re-read the hardware state and re-notify.
        self._resync_after_toggle()
        return True

    def _resync_after_toggle(self) -> None:
        """Re-reads the hardware state after a USB reset and re-notifies the GUI."""
        direct = self._driver.get_direct_mode()
        if direct is not None:
            self._direct_mode = bool(direct)
        self._notify("direct_mode_changed", self._direct_mode)

        scout = self._driver.get_scout_mode()
        if scout is not None:
            self._scout_mode = bool(scout)
        self._notify("scout_mode_changed", self._scout_mode)

    def get_direct_mode(self) -> bool:
        """Queries the card (not the local cache) for Direct Mode's state."""
        state = self._driver.get_direct_mode()
        if state is not None:
            self._direct_mode = bool(state)
        return self._direct_mode

    # ------------------------------------------------------------------
    # Sound mode (supported)
    # ------------------------------------------------------------------

    def list_sound_modes(self) -> list[tuple[str, str]]:
        """``(slug, label)`` list of the available sound modes.

        Order: default mode (``Disabled``) first, then alphabetical order
        of labels (order already used by :mod:`soundblaster_g8.sound_modes`).
        """
        return [(mode.slug, mode.label) for mode in SOUND_MODES.values()]

    def get_sound_mode(self) -> str:
        """Returns the active sound mode's slug (local state only).

        No read frame for the active mode has been identified in the
        captures (same as for Scout Mode): the state simply tracks the
        last successfully sent command.
        """
        return self._sound_mode

    def set_sound_mode(self, slug: str) -> bool:
        """Applies a sound mode (equalizer + acoustic engine).

        Returns:
            ``True`` if the card acknowledged every frame in the sequence.
        """
        mode = SOUND_MODES.get(slug)
        if mode is None:
            raise ValueError(f"Unknown sound mode: {slug}")

        ok = bool(self._driver.set_sound_mode(list(mode.writes)))
        if ok:
            self._sound_mode = slug
            self._eq_bands = list(mode.bands)
            self._eq_preamp = mode.preamp
            self._eq_enabled = mode.eq_enabled
            # A new mode fully replaces the bands: the old Bass/Treble
            # position (a delta from a base that no longer exists) no
            # longer makes sense.
            self._eq_bass = 0.0
            self._eq_treble = 0.0
            self._notify("sound_mode_changed", slug)
            self._notify("eq_all_bands_changed", self._eq_bands)
            self._notify("eq_preamp_changed", self._eq_preamp)
            self._notify("eq_enabled_changed", self._eq_enabled)
            self._notify("eq_bass_changed", 0.0)
            self._notify("eq_treble_changed", 0.0)
        else:
            self._notify("command_failed", "sound_mode", slug)
        return ok

    # ------------------------------------------------------------------
    # CrystalVoice (supported)
    # ------------------------------------------------------------------

    def set_crystalvoice_noise_reduction(self, enabled: bool) -> bool:
        ok = bool(self._driver.set_crystalvoice_noise_reduction(enabled))
        if ok:
            self._cv_noise_reduction = enabled
            self._notify("crystalvoice_noise_reduction_changed", enabled)
        else:
            self._notify("command_failed", "crystalvoice_noise_reduction", enabled)
        return ok

    def get_crystalvoice_noise_reduction(self) -> bool:
        return self._cv_noise_reduction

    def set_crystalvoice_noise_reduction_level(self, value: float) -> bool:
        clamped = max(0.0, min(1.0, value))
        ok = bool(self._driver.set_crystalvoice_noise_reduction_level(clamped))
        if ok:
            self._cv_noise_reduction_level = clamped
            self._notify("crystalvoice_noise_reduction_level_changed", clamped)
        else:
            self._notify("command_failed", "crystalvoice_noise_reduction_level", clamped)
        return ok

    def get_crystalvoice_noise_reduction_level(self) -> float:
        return self._cv_noise_reduction_level

    def set_crystalvoice_echo_cancellation(self, enabled: bool) -> bool:
        ok = bool(self._driver.set_crystalvoice_echo_cancellation(enabled))
        if ok:
            self._cv_echo_cancellation = enabled
            self._notify("crystalvoice_echo_cancellation_changed", enabled)
        else:
            self._notify("command_failed", "crystalvoice_echo_cancellation", enabled)
        return ok

    def get_crystalvoice_echo_cancellation(self) -> bool:
        return self._cv_echo_cancellation

    def set_crystalvoice_smart_volume(self, enabled: bool) -> bool:
        ok = bool(self._driver.set_crystalvoice_smart_volume(enabled))
        if ok:
            self._cv_smart_volume = enabled
            self._notify("crystalvoice_smart_volume_changed", enabled)
        else:
            self._notify("command_failed", "crystalvoice_smart_volume", enabled)
        return ok

    def get_crystalvoice_smart_volume(self) -> bool:
        return self._cv_smart_volume

    def set_crystalvoice_voice_morph(self, enabled: bool) -> bool:
        ok = bool(self._driver.set_crystalvoice_voice_morph(enabled))
        if ok:
            self._cv_voice_morph = enabled
            self._notify("crystalvoice_voice_morph_changed", enabled)
        else:
            self._notify("command_failed", "crystalvoice_voice_morph", enabled)
        return ok

    def get_crystalvoice_voice_morph(self) -> bool:
        return self._cv_voice_morph

    def set_crystalvoice_mic_equalizer(self, enabled: bool) -> bool:
        ok = bool(self._driver.set_crystalvoice_mic_equalizer(enabled))
        if ok:
            self._cv_mic_equalizer = enabled
            self._notify("crystalvoice_mic_equalizer_changed", enabled)
        else:
            self._notify("command_failed", "crystalvoice_mic_equalizer", enabled)
        return ok

    def get_crystalvoice_mic_equalizer(self) -> bool:
        return self._cv_mic_equalizer

    # --- CrystalVoice presets (Voice Morph / Microphone Equalizer) ---
    # Same contract as the sound modes: an ordered sequence of CMD_SET_FLOAT
    # writes replayed from the captures. The card has no read command for the
    # active preset (as for Scout Mode / Sound Mode), so ``get_*_preset``
    # tracks the last successfully sent command only.

    def list_voice_morph_presets(self) -> list[tuple[str, str]]:
        """``(slug, label)`` list of the available Voice Morph presets."""
        return [(preset.slug, preset.label) for preset in VOICE_MORPH_PRESETS.values()]

    def get_voice_morph_preset(self) -> str:
        """Active Voice Morph preset's slug (local state only)."""
        return self._cv_voice_morph_preset

    def set_voice_morph_preset(self, slug: str) -> bool:
        """Applies a Voice Morph preset.

        Returns:
            ``True`` if the card acknowledged every frame in the sequence.
        """
        return self._apply_crystalvoice_preset(
            VOICE_MORPH_PRESETS, slug, "_cv_voice_morph_preset",
            "crystalvoice_voice_morph_preset_changed", "voice_morph_preset",
        )

    def list_mic_equalizer_presets(self) -> list[tuple[str, str]]:
        """``(slug, label)`` list of the available Microphone Equalizer presets."""
        return [(preset.slug, preset.label) for preset in MIC_EQ_PRESETS.values()]

    def get_mic_equalizer_preset(self) -> str:
        """Active Microphone Equalizer preset's slug (local state only)."""
        return self._cv_mic_equalizer_preset

    def set_mic_equalizer_preset(self, slug: str) -> bool:
        """Applies a Microphone Equalizer preset.

        Returns:
            ``True`` if the card acknowledged every frame in the sequence.
        """
        return self._apply_crystalvoice_preset(
            MIC_EQ_PRESETS, slug, "_cv_mic_equalizer_preset",
            "crystalvoice_mic_equalizer_preset_changed", "mic_equalizer_preset",
        )

    def _apply_crystalvoice_preset(
        self, presets: dict, slug: str, attr: str, event: str, failure_name: str,
    ) -> bool:
        """Shared body of :meth:`set_voice_morph_preset`/:meth:`set_mic_equalizer_preset`."""
        preset = presets.get(slug)
        if preset is None:
            raise ValueError(f"Unknown CrystalVoice preset: {slug}")

        ok = bool(self._driver.set_crystalvoice_params(list(preset.writes)))
        if ok:
            setattr(self, attr, slug)
            self._notify(event, slug)
        else:
            self._notify("command_failed", failure_name, slug)
        return ok

    # ------------------------------------------------------------------
    # 10-band EQ (local state only for now)
    # ------------------------------------------------------------------

    def set_eq_band(self, index: int, value: float) -> bool:
        """Sets an equalizer band, with validation.

        Args:
            index: Band index (0-9)
            value: Value in dB (-12 to +12)
        """
        if not 0 <= index < self.NUM_BANDS:
            raise ValueError(f"Invalid band index: {index}")

        clamped = max(self.MIN_EQ_VALUE, min(self.MAX_EQ_VALUE, value))
        ok = bool(self._driver.eq_set_band(index, clamped))
        # Local state follows the slider even if the hardware hasn't
        # applied it yet, to keep the GUI consistent.
        self._eq_bands[index] = clamped
        self._notify("eq_band_changed", index, clamped)
        if not ok:
            self._notify("command_failed", "eq_band", index)
        return ok

    def get_eq_band(self, index: int) -> float:
        if not 0 <= index < self.NUM_BANDS:
            raise ValueError(f"Invalid band index: {index}")
        return self._eq_bands[index]

    def get_eq_all_bands(self) -> list[float]:
        return self._eq_bands.copy()

    def set_eq_preamp(self, value: float) -> bool:
        """Sets the Preamp, with the same validation as :meth:`set_eq_band`."""
        clamped = max(self.MIN_EQ_VALUE, min(self.MAX_EQ_VALUE, value))
        ok = bool(self._driver.eq_set_preamp(clamped))
        self._eq_preamp = clamped
        self._notify("eq_preamp_changed", clamped)
        if not ok:
            self._notify("command_failed", "eq_preamp", clamped)
        return ok

    def get_eq_preamp(self) -> float:
        return self._eq_preamp

    def prepare_eq_page(self) -> bool:
        """Prepares the equalizer for manual editing: enables it if needed.

        Native Creative app behavior when opening the Equalizer tab: if no
        equalizer is already active (mode "Disabled"), applies a **flat**
        equalizer (10 bands + Preamp at 0 dB) and enables it, rather than
        just setting the ``param 0x09`` bit while leaving the bands
        untouched - otherwise band writes are acknowledged by the card but
        remain inaudible while the EQ master is off. If a mode is already
        active (and thus already audible), does nothing.
        """
        if self._eq_enabled:
            return True

        writes: list[tuple[int, float]] = [(protocol.PARAM_EQ_ENABLED, 1.0)]
        writes += [(param, 0.0) for param in protocol.EQ_BAND_PARAMS]
        writes.append((protocol.PARAM_PREAMP, 0.0))

        ok = bool(self._driver.set_sound_mode(writes))
        if ok:
            self._eq_enabled = True
            self._eq_bands = [0.0] * self.NUM_BANDS
            self._eq_preamp = 0.0
            self._eq_bass = 0.0
            self._eq_treble = 0.0
            self._notify("eq_enabled_changed", True)
            self._notify("eq_all_bands_changed", self._eq_bands.copy())
            self._notify("eq_preamp_changed", 0.0)
            self._notify("eq_bass_changed", 0.0)
            self._notify("eq_treble_changed", 0.0)
        else:
            self._notify("command_failed", "eq_enabled", True)
        return ok

    def set_eq_bass(self, value: float) -> bool:
        """Sets the Bass slider's position (approximate, persistent).

        See ``BASS_TILT_WEIGHTS``: ``value`` is an absolute position
        (-12..12 dB, same range as the bands), not a delta.
        """
        return self._set_tilt_slider("_eq_bass", "eq_bass_changed", BASS_TILT_WEIGHTS, value)

    def get_eq_bass(self) -> float:
        return self._eq_bass

    def set_eq_treble(self, value: float) -> bool:
        """Sets the Treble slider's position (approximate, persistent)."""
        return self._set_tilt_slider(
            "_eq_treble", "eq_treble_changed", TREBLE_TILT_WEIGHTS, value
        )

    def get_eq_treble(self) -> float:
        return self._eq_treble

    def _set_tilt_slider(
        self, attr: str, event: str, weights: tuple[float, ...], value: float,
    ) -> bool:
        """Applies a Bass/Treble slider move across the 10 bands.

        Approximation derived from ``Equalizer-manual.pcapng`` (see
        ``BASS_TILT_WEIGHTS``/``TREBLE_TILT_WEIGHTS``): unlike a band or
        the Preamp, there's no dedicated parameter on the card - only the
        **delta** from the slider's previous position is weighted per band
        and added to the current state, which lets the slider stay
        wherever the user left it (a round trip exactly cancels its own
        effect).
        """
        clamped = max(self.MIN_EQ_VALUE, min(self.MAX_EQ_VALUE, value))
        delta = clamped - getattr(self, attr)

        all_ok = True
        if delta != 0.0:
            for i, weight in enumerate(weights):
                if weight == 0.0:
                    continue
                band_value = max(
                    self.MIN_EQ_VALUE, min(self.MAX_EQ_VALUE, self._eq_bands[i] + delta * weight)
                )
                self._eq_bands[i] = band_value
                if not self._driver.eq_set_band(i, band_value):
                    all_ok = False
            self._notify("eq_all_bands_changed", self._eq_bands.copy())

        setattr(self, attr, clamped)
        self._notify(event, clamped)
        if not all_ok:
            self._notify("command_failed", attr.lstrip("_"), clamped)
        return all_ok

    def load_preset(self, preset_name: str) -> bool:
        """Loads a predefined preset.

        Available presets: flat, bass_boost, vocal, gaming, movie.
        """
        presets = {
            "flat": [0.0] * self.NUM_BANDS,
            "bass_boost": [+4.0, +3.0, +2.0, +1.0, 0.0, 0.0, -1.0, -1.0, -2.0, -3.0],
            "vocal": [0.0, 0.0, 0.0, +2.0, +3.0, +2.0, 0.0, -1.0, -2.0, -3.0],
            "gaming": [+2.0, +3.0, +4.0, +3.0, +2.0, 0.0, -1.0, -2.0, -2.0, -3.0],
            "movie": [+3.0, +2.0, +1.0, 0.0, 0.0, 0.0, +1.0, +2.0, +3.0, +4.0],
        }

        if preset_name not in presets:
            raise ValueError(f"Unknown preset: {preset_name}")

        all_ok = True
        for i, value in enumerate(presets[preset_name]):
            self._eq_bands[i] = value
            if not self._driver.eq_set_band(i, value):
                all_ok = False
        self._notify("eq_all_bands_changed", presets[preset_name])
        return all_ok

    def save_preset(self, preset_name: str) -> bool:
        """Saves the equalizer's current state to the card."""
        return bool(self._driver.eq_save_preset(preset_name))

    # ------------------------------------------------------------------
    # Listeners / events
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
                print(f"[SoundBlasterController] Error in listener {event}: {exc}")


# Singleton controller
_controller_instance: Optional[SoundBlasterController] = None


def get_controller() -> SoundBlasterController:
    """Returns the controller's singleton instance."""
    global _controller_instance
    if _controller_instance is None:
        _controller_instance = SoundBlasterController()
    return _controller_instance
