"""
CrystalVoice page (Noise Reduction, Acoustic Echo Cancellation, Smart
Volume) for the Sound Blaster G8.

Page embedded in ``MainWindow`` (no floating window): see ``main_window.py``
for navigation (``_show_cv_page``/``_show_main_page``). All three toggles
and the Noise Reduction level slider use the same ``CMD_SET_FLOAT``
mechanism as the equalizer (see ``driver.set_crystalvoice_param``), but with
a dedicated TLV marker (``protocol.TLV_CRYSTALVOICE``) confirmed by the
``CrystalVoice-*.pcapng`` captures.
"""

import threading
import tkinter as tk
from typing import Callable, Optional

from ..controller import SoundBlasterController
from . import i18n, theme, widgets


class CrystalVoicePanel(tk.Frame):
    """Embedded page for the CrystalVoice sub-settings."""

    def __init__(
        self,
        parent,
        controller: SoundBlasterController,
        status_callback: Optional[Callable[..., None]] = None,
    ):
        """Initializes the CrystalVoice page.

        Args:
            parent: parent container (MainWindow's CrystalVoice page)
            controller: SoundBlaster controller instance
            status_callback: optional callback to display a toggle/slider
                write's status in the shared status bar; called as
                ``status_callback(msgid_template, **kwargs)``, matching
                ``MainWindow._set_status``'s signature
        """
        super().__init__(parent, bg=theme.BG_WINDOW)

        self.controller = controller
        self._status_callback = status_callback

        self._noise_reduction_var = tk.BooleanVar(value=controller.get_crystalvoice_noise_reduction())
        self._noise_reduction_level_var = tk.DoubleVar(
            value=round(controller.get_crystalvoice_noise_reduction_level() * 100)
        )
        self._echo_cancellation_var = tk.BooleanVar(value=controller.get_crystalvoice_echo_cancellation())
        self._smart_volume_var = tk.BooleanVar(value=controller.get_crystalvoice_smart_volume())

        self._setup_ui()

    def _setup_ui(self):
        """Sets up the CrystalVoice UI: a single card with 3 toggles + 1 slider."""
        #: (label_widget, translation_msgid) pairs for texts that need
        #: re-translating in place (retranslate()).
        self._section_labels: list[tuple[tk.Label, str]] = []

        container = tk.Frame(self, bg=theme.BG_WINDOW)
        container.pack(fill=tk.BOTH, expand=True, padx=36, pady=(16, 24))

        card = self._build_card(container, "CrystalVoice")

        self._nr_switch = self._add_toggle_row(
            card, "Noise Reduction", "", self._noise_reduction_var, self._on_noise_reduction_change,
        )
        self._level_slider, self._level_value_label = self._add_level_slider(
            card,
            "Reduce static background noises on outgoing audio during conference calls",
            self._noise_reduction_level_var,
        )

        self._add_separator(card)

        self._echo_switch = self._add_toggle_row(
            card, "Acoustic Echo Cancellation", "Eliminate echoes that interfere with conversation",
            self._echo_cancellation_var, self._on_echo_cancellation_change,
        )

        self._add_separator(card)

        self._smart_switch = self._add_toggle_row(
            card, "Smart Volume", "Be heard clearly without having to shout or whisper",
            self._smart_volume_var, self._on_smart_volume_change,
        )

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
        card.pack(fill=tk.X)

        inner = tk.Frame(card, bg=theme.BG_CARD)
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=18)
        return inner

    def _add_separator(self, parent) -> None:
        tk.Frame(parent, bg=theme.BORDER_CARD, height=1).pack(fill=tk.X, pady=16)

    def _add_toggle_row(
        self,
        parent,
        title_msgid: str,
        subtitle_msgid: str,
        variable: tk.BooleanVar,
        on_change: Callable[[], None],
    ) -> widgets.ToggleSwitch:
        """Builds a title/subtitle + toggle-switch row. Returns the switch."""
        row = tk.Frame(parent, bg=theme.BG_CARD)
        row.pack(fill=tk.X)

        text_frame = tk.Frame(row, bg=theme.BG_CARD)
        text_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        title_label = tk.Label(
            text_frame, text=i18n._(title_msgid), bg=theme.BG_CARD, fg=theme.FG_PRIMARY,
            font=theme.FONT_SECTION, anchor="w", justify=tk.LEFT,
        )
        title_label.pack(anchor="w")
        self._section_labels.append((title_label, title_msgid))

        if subtitle_msgid:
            subtitle_label = tk.Label(
                text_frame, text=i18n._(subtitle_msgid), bg=theme.BG_CARD, fg=theme.FG_SECONDARY,
                font=theme.FONT_SUBTITLE, anchor="w", justify=tk.LEFT, wraplength=380,
            )
            subtitle_label.pack(anchor="w", pady=(4, 0))
            self._section_labels.append((subtitle_label, subtitle_msgid))

        switch = widgets.ToggleSwitch(row, variable=variable, command=on_change, bg=theme.BG_CARD)
        switch.pack(side=tk.RIGHT, anchor="n")
        return switch

    def _add_level_slider(
        self, parent, label_msgid: str, var: tk.DoubleVar,
    ) -> tuple[widgets.Slider, tk.Label]:
        """Builds the Noise Reduction level slider (description + horizontal slider + %)."""
        wrap = tk.Frame(parent, bg=theme.BG_CARD)
        wrap.pack(fill=tk.X, pady=(14, 0))

        desc = tk.Label(
            wrap, text=i18n._(label_msgid), bg=theme.BG_CARD, fg=theme.FG_SECONDARY,
            font=theme.FONT_SUBTITLE, anchor="w", justify=tk.LEFT, wraplength=420,
        )
        desc.pack(anchor="w", pady=(0, 10))
        self._section_labels.append((desc, label_msgid))

        row = tk.Frame(wrap, bg=theme.BG_CARD)
        row.pack(fill=tk.X)

        value_label = tk.Label(
            row, text=f"{int(var.get())}%", anchor="center",
            bg=theme.BG_VALUE, fg=theme.FG_PRIMARY, font=theme.FONT_SMALL,
            padx=6, pady=4, width=5,
        )
        value_label.pack(side=tk.RIGHT, padx=(12, 0))

        def on_drag(value: float, _label=value_label):
            _label.config(text=f"{int(round(value))}%")

        slider = widgets.Slider(
            row, variable=var, from_=0, to=100, step=1,
            on_change=on_drag, on_release=self._commit_noise_reduction_level,
            bg=theme.BG_CARD, width=360, orientation="horizontal",
        )
        slider.pack(side=tk.LEFT, fill=tk.X, expand=True)

        return slider, value_label

    def retranslate(self) -> None:
        """Registered indirectly via ``MainWindow._retranslate``: re-applies
        every static text in place."""
        for label, msgid in self._section_labels:
            label.config(text=i18n._(msgid))

    def refresh(self) -> None:
        """Resynchronizes every control with the controller's known state.

        Called by ``MainWindow`` when the CrystalVoice page is shown, in
        case the state changed elsewhere since the panel was built.
        """
        self._noise_reduction_var.set(self.controller.get_crystalvoice_noise_reduction())
        level_pct = round(self.controller.get_crystalvoice_noise_reduction_level() * 100)
        self._noise_reduction_level_var.set(level_pct)
        self._level_value_label.config(text=f"{int(level_pct)}%")
        self._echo_cancellation_var.set(self.controller.get_crystalvoice_echo_cancellation())
        self._smart_volume_var.set(self.controller.get_crystalvoice_smart_volume())

    # ------------------------------------------------------------------
    # Toggles (run outside the GUI thread)
    # ------------------------------------------------------------------

    def _handle_toggle(
        self,
        label_msgid: str,
        var: tk.BooleanVar,
        switch: widgets.ToggleSwitch,
        setter: Callable[[bool], bool],
    ):
        """Runs a toggle in a worker thread, then resynchronizes the display."""
        requested = var.get()
        switch.set_enabled(False)
        label = i18n._(label_msgid)
        self._set_status("{label}: sending command…", label=label)

        def worker():
            error: Optional[Exception] = None
            ok = False
            try:
                ok = bool(setter(requested))
            except Exception as exc:  # pragma: no cover - depends on hardware
                error = exc
            self.after(0, lambda: self._finish_toggle(label, switch, var, requested, ok, error))

        threading.Thread(target=worker, name=f"g8-cv-{label_msgid}", daemon=True).start()

    def _finish_toggle(
        self,
        label: str,
        switch: widgets.ToggleSwitch,
        var: tk.BooleanVar,
        requested: bool,
        ok: bool,
        error: Optional[Exception],
    ):
        switch.set_enabled(True)
        effective = requested if ok else not requested
        var.set(effective)

        if error is not None:
            self._set_status("{label}: error ({error})", label=label, error=error)
        elif ok:
            self._set_status("{label} enabled" if effective else "{label} disabled", label=label)
        else:
            self._set_status("{label}: command failed (see console)", label=label)

    def _on_noise_reduction_change(self):
        self._handle_toggle(
            "Noise Reduction", self._noise_reduction_var, self._nr_switch,
            self.controller.set_crystalvoice_noise_reduction,
        )

    def _on_echo_cancellation_change(self):
        self._handle_toggle(
            "Acoustic Echo Cancellation", self._echo_cancellation_var, self._echo_switch,
            self.controller.set_crystalvoice_echo_cancellation,
        )

    def _on_smart_volume_change(self):
        self._handle_toggle(
            "Smart Volume", self._smart_volume_var, self._smart_switch,
            self.controller.set_crystalvoice_smart_volume,
        )

    # ------------------------------------------------------------------
    # Noise Reduction level (slider, commit on release)
    # ------------------------------------------------------------------

    def _commit_noise_reduction_level(self):
        """Sends the Noise Reduction level to the card (on thumb release)."""
        value = self._noise_reduction_level_var.get()
        label = i18n._("Noise Reduction")
        self._set_status("{label}: sending {value:.0f}%…", label=label, value=value)

        def worker():
            error: Optional[Exception] = None
            ok = False
            try:
                ok = bool(self.controller.set_crystalvoice_noise_reduction_level(value / 100.0))
            except Exception as exc:  # pragma: no cover - depends on hardware
                error = exc
            self.after(0, lambda: self._finish_level_commit(label, value, ok, error))

        threading.Thread(target=worker, name="g8-cv-noise-level", daemon=True).start()

    def _finish_level_commit(self, label: str, value: float, ok: bool, error: Optional[Exception]):
        if error is not None:
            self._set_status("{label}: error ({error})", label=label, error=error)
        elif ok:
            self._set_status("{label}: {value:.0f}% applied", label=label, value=value)
        else:
            self._set_status("{label}: command failed (see console)", label=label)

    def _set_status(self, template: str, **kwargs) -> None:
        if self._status_callback is not None:
            self._status_callback(template, **kwargs)
