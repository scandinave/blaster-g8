"""
Left navigation sidebar of the Sound Blaster G8 application.

Full-height column holding the application's main menu (only "Devices" and
"Settings" are implemented so far; "Playback" and "Recording" are built
disabled, awaiting their pages) and, at its foot, the two system volume
sliders - PC output and PC microphone.

Like the other panels (see ``decoder_panel.py``), this widget doesn't talk to
the outside world itself: it exposes ``on_select``/``on_output_volume``/
``on_input_volume`` callbacks and ``MainWindow`` wires them to the navigation
and to :mod:`soundblaster_g8.system_volume`.
"""

import tkinter as tk
from typing import Callable, Optional

from . import i18n, theme, widgets

#: Sidebar width in pixels, needed by MainWindow to size the window.
SIDEBAR_WIDTH = 200

#: Minimum height the sidebar needs for its menu and both volume rows. The
#: column ignores its children's requested size (pack_propagate(False)), so
#: without this the shorter pages would let the window shrink and clip the
#: sliders off the bottom.
SIDEBAR_MIN_HEIGHT = 420

#: (key, icon glyph, label msgid, implemented) for the menu entries. The
#: unimplemented ones are shown disabled rather than hidden: they advertise
#: what is coming without pretending to work.
MENU_DEFS = [
    ("devices", "device", "Devices", True),
    ("playback", "playback", "Playback", False),
    ("recording", "recording", "Recording", False),
    ("settings", "settings", "Settings", True),
]


def _border_frame(parent: tk.Misc) -> tk.Frame:
    """Fixed-width column drawing the sidebar's 1px right border.

    Tk frames only take an all-around border, so the separator is the sliver of
    parent frame left visible on the right of the sidebar itself.
    """
    outer = tk.Frame(
        parent, bg=theme.BORDER_CARD, width=SIDEBAR_WIDTH + 1, height=SIDEBAR_MIN_HEIGHT,
    )
    outer.pack(side=tk.LEFT, fill=tk.Y)
    outer.pack_propagate(False)
    return outer


class Sidebar(tk.Frame):
    """Navigation menu + system volume sliders.

    Packs itself (and its border column) on the left of ``parent``, so it must
    be built before whatever fills the rest of the window.
    """

    def __init__(
        self,
        parent: tk.Misc,
        on_select: Optional[Callable[[str], None]] = None,
        on_output_volume: Optional[Callable[[int], None]] = None,
        on_input_volume: Optional[Callable[[int], None]] = None,
    ):
        """Builds the sidebar.

        Args:
            parent: parent container (the main window)
            on_select: called with the key of a clicked (enabled) menu entry
            on_output_volume: called with the new PC output volume, 0-100,
                when the user releases the corresponding slider
            on_input_volume: same, for the PC microphone
        """
        super().__init__(_border_frame(parent), bg=theme.BG_CARD, width=SIDEBAR_WIDTH)
        self.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        # Fixed width: the menu rows and sliders must not stretch the column.
        self.pack_propagate(False)

        self._on_select = on_select
        self._items: dict[str, widgets.SidebarItem] = {}
        self._selected: Optional[str] = None

        self._build_volume_sliders(on_output_volume, on_input_volume)
        self._build_menu()

    def _build_menu(self) -> None:
        for key, icon, msgid, implemented in MENU_DEFS:
            item = widgets.SidebarItem(
                self, icon, i18n._(msgid),
                command=lambda k=key: self._on_item_click(k),
                bg=theme.BG_CARD, width=SIDEBAR_WIDTH,
            )
            item.pack(fill=tk.X, pady=(6, 0))
            if not implemented:
                item.set_enabled(False)
            self._items[key] = item

    def _build_volume_sliders(
        self,
        on_output_volume: Optional[Callable[[int], None]],
        on_input_volume: Optional[Callable[[int], None]],
    ) -> None:
        """Builds the two volume rows at the bottom (packed before the menu,
        so ``side=BOTTOM`` keeps them anchored to the foot of the column)."""
        self._input_slider = widgets.VolumeSlider(
            self, "microphone", command=on_input_volume, bg=theme.BG_CARD,
        )
        self._input_slider.pack(side=tk.BOTTOM, fill=tk.X, padx=16, pady=(0, 18))

        self._output_slider = widgets.VolumeSlider(
            self, "speaker", command=on_output_volume, bg=theme.BG_CARD,
        )
        self._output_slider.pack(side=tk.BOTTOM, fill=tk.X, padx=16, pady=(0, 14))

        divider = tk.Frame(self, bg=theme.BORDER_CARD, height=1)
        divider.pack(side=tk.BOTTOM, fill=tk.X, padx=16, pady=(0, 16))

    def _on_item_click(self, key: str) -> None:
        if self._on_select is not None:
            self._on_select(key)

    # ------------------------------------------------------------------
    # Public API (used by MainWindow)
    # ------------------------------------------------------------------

    def select(self, key: str) -> None:
        """Highlights one menu entry, un-highlighting the others."""
        if key == self._selected:
            return
        self._selected = key
        for item_key, item in self._items.items():
            item.set_selected(item_key == key)

    def set_output_volume(self, percent: Optional[int]) -> None:
        """Shows the PC output volume (``None`` = unreadable) without callback."""
        if not self._output_slider.is_dragging():
            self._output_slider.set_value(percent)

    def set_input_volume(self, percent: Optional[int]) -> None:
        """Shows the PC microphone volume (``None`` = unreadable), no callback."""
        if not self._input_slider.is_dragging():
            self._input_slider.set_value(percent)

    def set_output_enabled(self, enabled: bool) -> None:
        self._output_slider.set_enabled(enabled)

    def set_input_enabled(self, enabled: bool) -> None:
        self._input_slider.set_enabled(enabled)

    def retranslate(self) -> None:
        """Re-applies the menu labels in the current language, in place."""
        for key, _icon, msgid, _implemented in MENU_DEFS:
            self._items[key].set_text(i18n._(msgid))
