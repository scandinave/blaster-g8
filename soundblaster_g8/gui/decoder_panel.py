"""
Decoder page (Dolby Digital Dynamic Range Control) for the Sound Blaster G8.

Page embedded in ``MainWindow`` (no floating window): see ``main_window.py``
for navigation (``_show_decoder_page``/``_show_main_page``). The three modes
(Normal / Full / Night) are mutually exclusive and each one is a single
``CMD_SET_FLOAT`` write with a dedicated TLV marker
(``protocol.TLV_DECODER``), confirmed by a Wireshark capture -
same mechanism as the equalizer and CrystalVoice, see
``driver.set_decoder_mode``.

The card has no read command for the active mode (as for Scout Mode and
Sound Mode): the selected button reflects the last command it acknowledged,
so a refused write leaves the previous choice selected.
"""

import tkinter as tk
from typing import Callable, Optional

from ..controller import SoundBlasterController
from . import i18n, theme, widgets

#: Shared description shown above the three mode buttons.
DESCRIPTION = (
    "Play your Dolby Digital media with ease using this integrated decoder. "
    "With the Dynamic Range Control, wide volume swings between loud and quiet "
    "sounds can be customized to match your listening preferences, all without "
    "the loss of overall sound quality."
)


class DecoderPanel(tk.Frame):
    """Embedded page for the decoder's Dynamic Range Control modes."""

    def __init__(
        self,
        parent,
        controller: SoundBlasterController,
        status_callback: Optional[Callable[..., None]] = None,
    ):
        """Initializes the Decoder page.

        Args:
            parent: parent container (MainWindow's Decoder page)
            controller: SoundBlaster controller instance
            status_callback: optional callback to display a write's status in
                the shared status bar; called as
                ``status_callback(msgid_template, **kwargs)``, matching
                ``MainWindow._set_status``'s signature
        """
        super().__init__(parent, bg=theme.BG_WINDOW)

        self.controller = controller
        self._status_callback = status_callback

        #: Mode slugs, their translated labels and their buttons, all three
        #: parallel (labels re-filled on every retranslate).
        self._slugs: list[str] = []
        self._labels: list[str] = []
        self._buttons: list[widgets.RoundedButton] = []

        self._setup_ui()

    def _setup_ui(self):
        """Sets up the Decoder UI: a single card with a description and 3 buttons."""
        #: (label_widget, translation_msgid) pairs for texts that need
        #: re-translating in place (retranslate()).
        self._section_labels: list[tuple[tk.Label, str]] = []

        container = tk.Frame(self, bg=theme.BG_WINDOW)
        container.pack(fill=tk.BOTH, expand=True, padx=36, pady=(16, 24))

        card = self._build_card(container, "Decoder")

        desc = tk.Label(
            card, text=i18n._(DESCRIPTION), bg=theme.BG_CARD, fg=theme.FG_SECONDARY,
            font=theme.FONT_SUBTITLE, anchor="w", justify=tk.LEFT, wraplength=460,
        )
        desc.pack(anchor="w")
        self._section_labels.append((desc, DESCRIPTION))

        row = tk.Frame(card, bg=theme.BG_CARD)
        row.pack(anchor="w", pady=(18, 0))

        for slug, label in self.controller.list_decoder_modes():
            text = i18n.decoder_mode_label(slug, label)
            button = widgets.RoundedButton(
                row,
                text=text,
                command=lambda s=slug: self._on_mode_click(s),
                bg=theme.BG_CARD,
                padx=22,
            )
            button.pack(side=tk.LEFT, padx=(0, 12))
            self._slugs.append(slug)
            self._labels.append(text)
            self._buttons.append(button)

        self._select_button(self.controller.get_decoder_mode())

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

    def _select_button(self, slug: str) -> None:
        """Highlights the button matching ``slug`` (accent fill), greys the others."""
        for button, button_slug in zip(self._buttons, self._slugs):
            button.set_fill(theme.ACCENT if button_slug == slug else theme.BG_CONTROL)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        for button in self._buttons:
            button.set_enabled(enabled)

    def retranslate(self) -> None:
        """Registered indirectly via ``MainWindow._retranslate``: re-applies
        every static text in place."""
        for label, msgid in self._section_labels:
            label.config(text=i18n._(msgid))
        for i, (slug, label) in enumerate(self.controller.list_decoder_modes()):
            self._labels[i] = i18n.decoder_mode_label(slug, label)
            # set_text() redraws with the stored fill: the selection survives.
            self._buttons[i].set_text(self._labels[i])

    def refresh(self) -> None:
        """Resynchronizes the selection with the controller's known state.

        Called by ``MainWindow`` when the Decoder page is shown, in case the
        state changed elsewhere since the panel was built.
        """
        self._select_button(self.controller.get_decoder_mode())

    # ------------------------------------------------------------------
    # Mode selection (runs outside the GUI thread)
    # ------------------------------------------------------------------

    def _on_mode_click(self, slug: str) -> None:
        """Applies a decoder mode in a worker thread, like the CrystalVoice presets."""
        if slug not in self._slugs:
            return
        label = i18n._("Decoder")
        mode = self._labels[self._slugs.index(slug)]

        self._set_buttons_enabled(False)
        self._set_status('{label}: sending "{mode}"…', label=label, mode=mode)

        def worker():
            error: Optional[Exception] = None
            ok = False
            try:
                ok = bool(self.controller.set_decoder_mode(slug))
            except Exception as exc:  # pragma: no cover - depends on hardware
                error = exc
            self.after(0, lambda: self._finish_mode_change(label, mode, ok, error))

        self.controller.submit(worker)

    def _finish_mode_change(
        self, label: str, mode: str, ok: bool, error: Optional[Exception],
    ) -> None:
        self._set_buttons_enabled(True)

        # On failure, resynchronize the selection with the controller's real state.
        self._select_button(self.controller.get_decoder_mode())

        if error is not None:
            self._set_status("{label}: error ({error})", label=label, error=error)
        elif ok:
            self._set_status('{label}: "{mode}" applied', label=label, mode=mode)
        else:
            self._set_status(
                '{label}: "{mode}" failed (see console)', label=label, mode=mode
            )

    def _set_status(self, template: str, **kwargs) -> None:
        if self._status_callback is not None:
            self._status_callback(template, **kwargs)
