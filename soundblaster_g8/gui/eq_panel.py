"""
Equalizer page (10 bands + Preamp/Bass/Treble) for the Sound Blaster G8.

Page embedded in ``MainWindow`` (no floating window): see ``main_window.py``
for navigation (``_show_eq_page``/``_show_main_page``). Each band and the
Preamp use the same hardware-validated mechanism as Sound Mode
(``CMD_SET_FLOAT``, see ``driver.eq_set_band``/``driver.eq_set_preamp``).
Bass and Treble have no dedicated parameter on the card: see
``controller.set_eq_bass``/``set_eq_treble`` for the approximation used
(derived from the ``Equalizer-manual.pcapng`` capture) - these two sliders
stay wherever the user leaves them (like the native Creative app), the
controller only keeping an internal delta.

Cards and sliders follow the design mockup's style (dark background, thin
track + round thumb): see ``theme.py``/``widgets.py``.
"""

import tkinter as tk
from typing import Callable, Optional

from ..controller import SoundBlasterController
from . import i18n, theme, widgets

#: Preset name -> display-text msgid (identity translation in both
#: languages - these are already language-neutral preset names).
PRESET_LABELS = {
    "flat": "Flat",
    "bass_boost": "Bass Boost",
    "vocal": "Vocal",
    "gaming": "Gaming",
    "movie": "Movie",
}


class EQPanel(tk.Frame):
    """Embedded page for the 10-band equalizer + Preamp/Bass/Treble."""

    FREQUENCY_BANDS = [
        "32 Hz", "64 Hz", "125 Hz", "250 Hz", "500 Hz",
        "1 kHz", "2 kHz", "4 kHz", "8 kHz", "16 kHz"
    ]

    #: Track height of the vertical sliders (Bands/Preamp/Tone).
    SLIDER_HEIGHT = 180

    def __init__(
        self,
        parent,
        controller: SoundBlasterController,
        status_callback: Optional[Callable[..., None]] = None,
    ):
        """Initializes the EQ page.

        Args:
            parent: parent container (MainWindow's EQ page)
            controller: SoundBlaster controller instance
            status_callback: optional callback to display a band/slider
                write's status in the shared status bar; called as
                ``status_callback(msgid_template, **kwargs)``, matching
                ``MainWindow._set_status``'s signature
        """
        super().__init__(parent, bg=theme.BG_WINDOW)

        self.controller = controller
        self._status_callback = status_callback
        self._band_vars: list[tk.DoubleVar] = []
        self._preamp_var = tk.DoubleVar(value=controller.get_eq_preamp())
        # Bass/Treble have no dedicated parameter on the card, but their
        # position stays displayed as the user left it (see
        # controller.set_eq_bass/set_eq_treble).
        self._bass_var = tk.DoubleVar(value=controller.get_eq_bass())
        self._treble_var = tk.DoubleVar(value=controller.get_eq_treble())

        # Load the current bands
        eq_bands = controller.get_eq_all_bands()
        for value in eq_bands:
            var = tk.DoubleVar(value=value)
            self._band_vars.append(var)

        self._setup_ui()

    def _setup_ui(self):
        """Sets up the equalizer UI.

        Vertical sliders side by side in a single row, in the order
        Bands -> Preamp -> Tone (each group keeps its own label, a thin
        separator visually distinguishes them without going back to
        separate stacked cards).
        """
        self._sliders: list[widgets.Slider] = []
        self._labels: list[tk.Label] = []
        #: (label_widget, translation_msgid) pairs for section titles that
        #: need re-translating in place (retranslate()).
        self._section_labels: list[tuple[tk.Label, str]] = []
        #: RoundedButton preset widgets, keyed by preset name, for retranslate().
        self._preset_buttons: dict[str, widgets.RoundedButton] = {}

        container = tk.Frame(self, bg=theme.BG_WINDOW)
        container.pack(fill=tk.BOTH, expand=True, padx=36, pady=(16, 0))

        sliders_card = self._build_card(container, "Equalizer")
        row = tk.Frame(sliders_card, bg=theme.BG_CARD)
        row.pack(anchor="w")

        # Bands (10 columns)
        bands_group = self._build_group(row, "Bands")
        for i in range(len(self._band_vars)):
            slider, label = self._add_slider_column(
                bands_group, self.FREQUENCY_BANDS[i], self._band_vars[i],
                lambda idx=i: self._commit_band(idx),
            )
            self._sliders.append(slider)
            self._labels.append(label)

        self._add_group_separator(row)

        # Preamp - same mechanics as a band (dedicated parameter, exact)
        preamp_group = self._build_group(row, "Preamp")
        self._preamp_slider, self._preamp_label = self._add_slider_column(
            preamp_group, "Gain", self._preamp_var, self._commit_preamp,
        )

        self._add_group_separator(row)

        # Bass / Treble - approximation (see module docstring)
        tilt_group = self._build_group(row, "Tone (approximate)")
        self._bass_slider, self._bass_label = self._add_slider_column(
            tilt_group, "Bass", self._bass_var,
            lambda: self._commit_tilt(i18n._("Bass"), self._bass_var, self.controller.set_eq_bass),
        )
        self._treble_slider, self._treble_label = self._add_slider_column(
            tilt_group, "Treble", self._treble_var,
            lambda: self._commit_tilt(i18n._("Treble"), self._treble_var, self.controller.set_eq_treble),
        )

        # Presets frame
        presets_card = self._build_card(container, "Quick Presets")
        preset_row = tk.Frame(presets_card, bg=theme.BG_CARD)
        preset_row.pack(fill=tk.X)
        for preset in ("flat", "bass_boost", "vocal", "gaming", "movie"):
            button = widgets.RoundedButton(
                preset_row,
                text=i18n._(PRESET_LABELS[preset]),
                command=lambda p=preset: self._apply_preset(p),
                icon="equalizer",
                bg=theme.BG_CARD,
                fill=theme.BG_CONTROL,
                fg=theme.FG_PRIMARY,
                font=theme.FONT_BODY,
                padx=16,
                pady=10,
            )
            button.pack(side=tk.LEFT, padx=(0, 12))
            self._preset_buttons[preset] = button

        # Reset command
        cmd_frame = tk.Frame(container, bg=theme.BG_WINDOW)
        cmd_frame.pack(fill=tk.X, pady=(0, 20))
        self._reset_button = widgets.RoundedButton(
            cmd_frame,
            text=i18n._("Reset All"),
            command=self._reset_all,
            icon="reset",
            bg=theme.BG_WINDOW,
            fill=theme.BG_CONTROL,
            fg=theme.FG_PRIMARY,
            font=theme.FONT_BODY,
            padx=16,
            pady=10,
        )
        self._reset_button.pack(side=tk.RIGHT)

    def _build_card(self, parent, title_msgid: str) -> tk.Frame:
        """Builds a section card (label + bordered frame) and returns the inside."""
        label = tk.Label(
            parent, text=i18n._(title_msgid), bg=theme.BG_WINDOW, fg=theme.FG_LABEL,
            font=theme.FONT_LABEL, anchor="w",
        )
        label.pack(fill=tk.X, pady=(0, 10))
        self._section_labels.append((label, title_msgid))

        card = tk.Frame(
            parent, bg=theme.BG_CARD, highlightbackground=theme.BORDER_CARD,
            highlightthickness=1, bd=0,
        )
        card.pack(fill=tk.X, pady=(0, 20))

        inner = tk.Frame(card, bg=theme.BG_CARD)
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=18)
        return inner

    def _build_group(self, parent, title_msgid: str) -> tk.Frame:
        """Sub-group of columns (title + row of vertical sliders).

        Packed side by side with the other groups (``pack(side=tk.LEFT)``)
        in the same row: keeps a visual/label grouping without going back
        to separate cards stacked vertically.
        """
        group = tk.Frame(parent, bg=theme.BG_CARD)
        group.pack(side=tk.LEFT, anchor="n")

        label = tk.Label(
            group, text=i18n._(title_msgid), bg=theme.BG_CARD, fg=theme.FG_LABEL,
            font=theme.FONT_LABEL, anchor="w",
        )
        label.pack(fill=tk.X, pady=(0, 12))
        self._section_labels.append((label, title_msgid))

        columns = tk.Frame(group, bg=theme.BG_CARD)
        columns.pack()
        return columns

    def _add_group_separator(self, parent) -> None:
        """Thin separator between two column groups."""
        tk.Frame(parent, bg=theme.BORDER_CARD, width=1).pack(
            side=tk.LEFT, fill=tk.Y, padx=16, pady=4,
        )

    def _add_slider_column(
        self,
        parent,
        label_msgid: str,
        var: tk.DoubleVar,
        on_release: Callable[[], None],
    ) -> tuple[widgets.Slider, tk.Label]:
        """Builds a vertical slider column (value, thumb, label).

        The thumb follows the drag (local display); the hardware write
        happens on release (``on_release``) so the HID control channel
        isn't flooded.
        """
        column = tk.Frame(parent, bg=theme.BG_CARD)
        column.pack(side=tk.LEFT, padx=8)

        value_label = tk.Label(
            column, text=f"{var.get():+.1f} dB", anchor="center",
            bg=theme.BG_VALUE, fg=theme.FG_PRIMARY, font=theme.FONT_SMALL,
            padx=4, pady=4,
        )
        value_label.pack(pady=(0, 10))

        def on_drag(value: float, _label=value_label):
            _label.config(text=f"{value:+.1f} dB")

        slider = widgets.Slider(
            column, variable=var, from_=-12, to=12, step=0.5,
            on_change=on_drag, on_release=on_release, bg=theme.BG_CARD,
            height=self.SLIDER_HEIGHT, orientation="vertical",
        )
        slider.pack()

        name_label = tk.Label(
            column, text=i18n._(label_msgid), anchor="center",
            bg=theme.BG_CARD, fg=theme.FG_PRIMARY, font=theme.FONT_BODY,
        )
        name_label.pack(pady=(10, 0))
        self._section_labels.append((name_label, label_msgid))

        return slider, value_label

    def retranslate(self) -> None:
        """Registered indirectly via ``MainWindow._retranslate``: re-applies
        every static text in place (band/frequency labels, section titles,
        preset and reset buttons). Numeric value labels (dB) need no
        translation."""
        for label, msgid in self._section_labels:
            label.config(text=i18n._(msgid))
        for preset, button in self._preset_buttons.items():
            button.set_text(i18n._(PRESET_LABELS[preset]))
        self._reset_button.set_text(i18n._("Reset All"))

    def refresh(self) -> None:
        """Resynchronizes all sliders with the controller's known state.

        Called by ``MainWindow`` after a sound-mode selection or a "flat"
        equalizer activation (``prepare_eq_page``), which replace the
        bands/Preamp and reset Bass/Treble to 0 without going through this
        page.
        """
        eq_bands = self.controller.get_eq_all_bands()
        for i, var in enumerate(self._band_vars):
            if i < len(eq_bands):
                var.set(eq_bands[i])
                self._labels[i].config(text=f"{eq_bands[i]:+.1f} dB")
        preamp = self.controller.get_eq_preamp()
        self._preamp_var.set(preamp)
        self._preamp_label.config(text=f"{preamp:+.1f} dB")
        bass = self.controller.get_eq_bass()
        self._bass_var.set(bass)
        self._bass_label.config(text=f"{bass:+.1f} dB")
        treble = self.controller.get_eq_treble()
        self._treble_var.set(treble)
        self._treble_label.config(text=f"{treble:+.1f} dB")

    def _commit_band(self, index: int):
        """Sends a band's value to the card (on thumb release)."""
        if not (0 <= index < len(self._band_vars)):
            return
        value = self._band_vars[index].get()
        label = i18n._("Band {band}").format(band=self.FREQUENCY_BANDS[index])
        self._run_commit(
            label, value,
            lambda: self.controller.set_eq_band(index, value),
        )

    def _commit_preamp(self):
        """Sends the Preamp value to the card (on thumb release)."""
        value = self._preamp_var.get()
        self._run_commit(
            i18n._("Preamp"), value,
            lambda: self.controller.set_eq_preamp(value),
        )

    def _commit_tilt(self, label: str, var: tk.DoubleVar, setter: Callable[[float], bool]):
        """Sends a new Bass/Treble position (approximate).

        The slider stays wherever the user left it (see
        ``controller.set_eq_bass``/``set_eq_treble``): only the 10 displayed
        bands are resynchronized afterwards, since the approximation
        modifies all of them.
        """
        value = var.get()
        self._set_status("{label}: sending {value:+.1f} dB (approximate)…", label=label, value=value)

        def worker():
            error: Optional[Exception] = None
            ok = False
            try:
                ok = bool(setter(value))
            except Exception as exc:  # pragma: no cover - depends on hardware
                error = exc
            self.after(0, lambda: self._finish_tilt(label, value, ok, error))

        self.controller.submit(worker)

    def _finish_tilt(self, label: str, value: float, ok: bool, error: Optional[Exception]):
        self.refresh()
        if error is not None:
            self._set_status("{label}: error ({error})", label=label, error=error)
        elif ok:
            self._set_status("{label}: {value:+.1f} dB applied (approximate)", label=label, value=value)
        else:
            self._set_status("{label}: command failed (see console)", label=label)

    def _run_commit(self, label: str, value: float, action: Callable[[], bool]):
        """Runs a single hardware write in a worker thread."""
        self._set_status("{label}: sending {value:+.1f} dB…", label=label, value=value)

        def worker():
            error: Optional[Exception] = None
            ok = False
            try:
                ok = bool(action())
            except Exception as exc:  # pragma: no cover - depends on hardware
                error = exc
            self.after(0, lambda: self._finish_commit(label, value, ok, error))

        self.controller.submit(worker)

    def _finish_commit(self, label: str, value: float, ok: bool, error: Optional[Exception]):
        if error is not None:
            self._set_status("{label}: error ({error})", label=label, error=error)
        elif ok:
            self._set_status("{label}: {value:+.1f} dB applied", label=label, value=value)
        else:
            self._set_status("{label}: command failed (see console)", label=label)

    def _set_status(self, template: str, **kwargs) -> None:
        if self._status_callback is not None:
            self._status_callback(template, **kwargs)

    def _apply_preset(self, preset_name: str):
        """Applies a preset to all bands."""
        self.controller.load_preset(preset_name)
        self.refresh()
        label = i18n._(PRESET_LABELS.get(preset_name, preset_name))
        self._set_status('Preset "{label}" applied', label=label)

    def _reset_all(self):
        """Resets all bands to 0 dB."""
        self._apply_preset("flat")
