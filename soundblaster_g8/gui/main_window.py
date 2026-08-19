"""
MainWindow for the Sound Blaster G8 control application.
Dark-themed Tkinter interface (see ``theme.py``/``widgets.py``), matching the
"Sound Blaster G8.dc.html" design mockup (product photo, icon badges, "split
button" style sound-mode selector).

Hardware commands run off the Tk thread, on the controller's shared worker
(``controller.submit``): toggling Direct Mode triggers a USB reset on the card
and takes 2 to 4 seconds, which would freeze the window if done in the Tk
callback. Commands are executed one at a time, in submission order, and the
result is brought back to the GUI thread via ``self.after(0, ...)``.

The window holds five "pages" (main page / Equalizer page / CrystalVoice
page / Decoder page / Settings page) in the same container, only one packed
at a time (no floating window): see ``_show_main_page``/``_show_eq_page``/
``_show_cv_page``/``_show_decoder_page``/``_show_settings_page``. They live
in the right-hand column, next to the full-height navigation sidebar
(``sidebar.py``); the Equalizer, CrystalVoice and Decoder pages stay
sub-pages of "Devices", reached by clicking a row and left with the Back
button, so "Devices" remains the selected menu entry throughout, while
Settings is its own top-level sidebar destination (no Back button).

The sidebar's two volume sliders drive the *system* volume (see
``system_volume.py``), not the card's own registers: they go through the same
worker thread as hardware commands, because they shell out to ``pactl`` /
``osascript``.
"""

import tkinter as tk
from pathlib import Path
from typing import Callable, Optional

from .. import alsa_fix, system_volume
from ..controller import SoundBlasterController
from ..driver import PRODUCT_ID, VENDOR_ID
from . import i18n, theme, widgets
from .crystalvoice_panel import CrystalVoicePanel
from .decoder_panel import DecoderPanel
from .eq_panel import EQPanel
from .sidebar import SIDEBAR_WIDTH, Sidebar

MIN_WINDOW_WIDTH = 640 + SIDEBAR_WIDTH
ASSETS_DIR = Path(__file__).parent / "assets"

#: (feature key, icon glyph, title msgid, subtitle msgid) for the two
#: toggle rows on the main page.
TOGGLE_DEFS = [
    ("direct_mode", "direct", "Direct Mode", "No signal processing"),
    ("scout_mode", "scout", "Scout Mode", "In-game sound detection"),
]

#: (feature key, icon glyph, title msgid, subtitle msgid) for the toggle
#: rows on the Settings page.
SETTINGS_TOGGLE_DEFS = [
    ("logo_led", "led", "Logo LED", "Illuminates the G8's logo"),
    ("energy_saving", "energy_saving", "Power Saving", "Reduces power use when idle"),
]


class MainWindow(tk.Tk):
    """Main window of the Sound Blaster G8 application."""

    def __init__(self):
        """Initializes the main window."""
        # Sets WM_CLASS to ("soundblaster-g8", "Soundblaster-g8"). The
        # instance field has to stay equal to StartupWMClass in
        # packaging/soundblaster-g8.desktop - that is how the desktop shell
        # ties the window to its .desktop entry, and hence to the name and
        # icon it shows in the taskbar. When the two drifted apart, COSMIC
        # fell back to the process name and displayed "python3.12" with no
        # icon.
        super().__init__(baseName="soundblaster-g8", className="soundblaster-g8")

        i18n.load_saved_language()

        self.title(i18n._("Sound Blaster G8 - Control"))
        self.resizable(True, True)
        # 128x128 rather than the full-size icon.png: Tk keeps the image
        # uncompressed (32 bits/pixel) and pushes a second copy to the X
        # server, so the 512x512 version costs 3 MB of RSS against 0.2 MB
        # here - for an icon no window manager displays above 128px. The
        # 512x512 file stays on disk for the hicolor theme (debian/rules).
        self._app_icon_image = tk.PhotoImage(file=str(ASSETS_DIR / "icon-128.png"))
        self.iconphoto(True, self._app_icon_image)

        # Controller singleton
        self._controller: Optional[SoundBlasterController] = None

        # Toggle state
        self._direct_mode_var = tk.BooleanVar(value=False)
        self._scout_mode_var = tk.BooleanVar(value=False)
        self._logo_led_var = tk.BooleanVar(value=False)
        self._energy_saving_var = tk.BooleanVar(value=False)

        # Sound mode: parallel lists (slugs/labels) driving the SplitSelect.
        self._sound_mode_slugs: list[str] = []
        self._sound_mode_labels: list[str] = []

        # Unavailable switches (feature not yet reverse-engineered): must
        # not be re-enabled at the end of a command.
        self._unavailable: set[str] = set()
        self._switches: dict[str, widgets.ToggleSwitch] = {}
        self._toggle_rows: dict[str, dict] = {}
        self._eq_enabled = True
        self._cv_enabled = True
        self._decoder_enabled = True

        # Title of the page currently shown, as (msgid, font), so it can be
        # re-rendered in place when the language changes (see _show_page).
        self._current_title: tuple[str, tuple] = ("Sound Blaster G8", theme.FONT_TITLE)

        # Last status message shown, as (msgid_template, kwargs), so it can
        # be re-rendered in place when the language changes.
        self._last_status: tuple[str, dict] = ("Ready", {})

        # System volume (sidebar sliders): handle of the background watcher,
        # kept so it can be stopped when the window closes; id of the pending
        # "re-enable the sliders" job scheduled after a Direct Mode
        # re-enumeration (see _on_reconnecting); and which of the two volumes
        # the platform actually lets us read, so a slider is never re-enabled
        # for a device that has no volume control.
        self._volume_watcher = None
        self._volume_reenable_job: Optional[str] = None
        self._volume_readable = {system_volume.OUTPUT: False, system_volume.INPUT: False}

        # Window setup
        self._setup_ui()

    def _setup_ui(self):
        """Sets up the UI: sidebar, header, pages, status bar."""
        theme.apply_theme(self)

        # Sidebar first: it packs itself on the left, and the content column
        # then takes whatever is left.
        self._sidebar = Sidebar(
            self,
            on_select=self._on_sidebar_select,
            on_output_volume=self._on_output_volume_change,
            on_input_volume=self._on_input_volume_change,
        )
        self._content = tk.Frame(self, bg=theme.BG_WINDOW)
        self._content.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)

        self._setup_header()
        i18n.add_listener(self._retranslate)

        # Pages container: main_page and eq_page are siblings, only one is
        # packed at a time (see _show_main_page/_show_eq_page).
        self._pages_container = tk.Frame(self._content, bg=theme.BG_WINDOW)
        self._pages_container.pack(expand=True, fill=tk.BOTH)

        self._main_page = tk.Frame(self._pages_container, bg=theme.BG_WINDOW)
        self._eq_page = tk.Frame(self._pages_container, bg=theme.BG_WINDOW)
        self._cv_page = tk.Frame(self._pages_container, bg=theme.BG_WINDOW)
        self._decoder_page = tk.Frame(self._pages_container, bg=theme.BG_WINDOW)
        self._settings_page = tk.Frame(self._pages_container, bg=theme.BG_WINDOW)
        self._pages = (
            self._main_page, self._eq_page, self._cv_page, self._decoder_page,
            self._settings_page,
        )

        self._setup_main_page(self._main_page)
        self._setup_settings_page(self._settings_page)
        # The panels need the controller, built right below: see
        # _ensure_eq_panel & co., eagerly called after _init_controller so
        # every page's real content is in place before _fit_window_to_content
        # measures them.
        self._eq_panel: Optional[EQPanel] = None
        self._cv_panel: Optional[CrystalVoicePanel] = None
        self._decoder_panel: Optional[DecoderPanel] = None

        # Status bar (shared between both pages)
        status_bar = tk.Frame(self._content, bg=theme.BG_WINDOW)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self._status_label = tk.Label(
            status_bar,
            text="",
            anchor=tk.W,
            bg=theme.BG_WINDOW,
            fg=theme.FG_STATUSBAR,
            font=theme.FONT_SMALL,
            padx=24,
            pady=10,
        )
        self._status_label.pack(expand=True, fill=tk.X)
        self._render_status()

        divider = tk.Frame(self._content, bg=theme.BORDER_CARD, height=1)
        divider.pack(fill=tk.X, side=tk.BOTTOM)

        # Controller initialization: must happen before the panels are built
        # (they read the controller) and before the window is sized (feature
        # availability graying affects some rows' requested size).
        self._init_controller()
        self._ensure_eq_panel()
        self._ensure_cv_panel()
        self._ensure_decoder_panel()

        self._fit_window_to_content()
        self._show_main_page()

        self._init_system_volume()

    def _setup_header(self):
        """Shared header: back button (hidden on the main page) + title + language selector."""
        header = tk.Frame(self._content, bg=theme.BG_WINDOW, height=64)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        self._back_button = widgets.RoundedButton(
            header,
            text=i18n._("←  Back"),
            command=self._show_main_page,
            bg=theme.BG_WINDOW,
            fill=theme.BG_CONTROL,
            fg=theme.FG_PRIMARY,
            font=theme.FONT_BUTTON,
            padx=16,
            pady=8,
        )
        # Placed/hidden dynamically by _show_main_page/_show_eq_page.

        self._title_label = tk.Label(
            header,
            text=i18n._("Sound Blaster G8"),
            bg=theme.BG_WINDOW,
            fg=theme.FG_PRIMARY,
            font=theme.FONT_TITLE,
        )
        self._title_label.place(relx=0.5, rely=0.5, anchor="center")

        # Language selector: option list built from whatever locales are
        # actually discovered under soundblaster_g8/locale/ (see
        # i18n.available_languages) - not hardcoded, so a new compiled
        # locale shows up here automatically on the next launch.
        languages = i18n.available_languages()
        self._lang_codes = [code for code, _name in languages]
        lang_names = [name for _code, name in languages]
        lang_width = widgets.SplitSelect.compute_width(lang_names, font=theme.FONT_SMALL)
        self._lang_select = widgets.SplitSelect(
            header, values=lang_names, command=self._on_language_change,
            bg=theme.BG_WINDOW, width=lang_width, font=theme.FONT_SMALL,
        )
        self._lang_select.place(relx=1.0, rely=0.5, anchor="e", x=-16)
        if i18n.get_language() in self._lang_codes:
            self._lang_select.set_index(self._lang_codes.index(i18n.get_language()))

        self._header_frame = header

    def _setup_main_page(self, controls_frame_parent):
        """Builds the main page content: product photo + 2-column grid."""
        outer = tk.Frame(controls_frame_parent, bg=theme.BG_WINDOW)
        outer.pack(expand=True, fill=tk.BOTH, padx=32, pady=(20, 24))

        self._build_photo_header(outer)

        grid = tk.Frame(outer, bg=theme.BG_WINDOW)
        grid.pack(fill=tk.BOTH, expand=True)
        grid.columnconfigure(0, weight=1, uniform="col")
        grid.columnconfigure(1, weight=1, uniform="col")

        left = tk.Frame(grid, bg=theme.BG_WINDOW)
        right = tk.Frame(grid, bg=theme.BG_WINDOW)
        left.grid(row=0, column=0, sticky="new", padx=(0, 12))
        right.grid(row=0, column=1, sticky="new", padx=(12, 0))

        for key, icon, title_msgid, subtitle_msgid in TOGGLE_DEFS:
            var = {
                "direct_mode": self._direct_mode_var,
                "scout_mode": self._scout_mode_var,
            }[key]
            handler = {
                "direct_mode": self._on_direct_mode_change,
                "scout_mode": self._on_scout_mode_change,
            }[key]
            self._toggle_rows[key] = self._build_toggle_row(
                left, icon, title_msgid, subtitle_msgid, var, handler,
            )

        self._direct_toggle_switch = self._toggle_rows["direct_mode"]["switch"]
        self._scout_toggle_switch = self._toggle_rows["scout_mode"]["switch"]

        self._build_decoder_row(left)

        self._build_sound_mode_row(right)
        self._build_equalizer_row(right)
        self._build_crystalvoice_row(right)

    def _setup_settings_page(self, controls_frame_parent):
        """Builds the Settings page content: Logo LED and Power Saving toggles."""
        outer = tk.Frame(controls_frame_parent, bg=theme.BG_WINDOW)
        outer.pack(expand=True, fill=tk.BOTH, padx=32, pady=(20, 24))

        for key, icon, title_msgid, subtitle_msgid in SETTINGS_TOGGLE_DEFS:
            var = {
                "logo_led": self._logo_led_var,
                "energy_saving": self._energy_saving_var,
            }[key]
            handler = {
                "logo_led": self._on_logo_led_change,
                "energy_saving": self._on_energy_saving_change,
            }[key]
            self._toggle_rows[key] = self._build_toggle_row(
                outer, icon, title_msgid, subtitle_msgid, var, handler,
            )

        self._led_toggle_switch = self._toggle_rows["logo_led"]["switch"]
        self._energy_toggle_switch = self._toggle_rows["energy_saving"]["switch"]

    def _build_photo_header(self, parent):
        """Shows the product photo (rounded corners) at the top of the main page."""
        photo_path = ASSETS_DIR / "g8_photo.png"
        if not photo_path.exists():
            return
        # Reference kept on self: otherwise the PhotoImage gets garbage-collected.
        self._g8_photo_image = tk.PhotoImage(file=str(photo_path))
        tk.Label(
            parent, image=self._g8_photo_image, bg=theme.BG_WINDOW, bd=0, highlightthickness=0,
        ).pack(pady=(0, 24))

    def _build_row_icon_text(self, parent, icon: str, title: str, subtitle: str, subtitle_wrap: int = 280):
        """Builds an icon-badge + title/subtitle row. Returns (row, badge, title, subtitle)."""
        row = tk.Frame(parent, bg=theme.BG_WINDOW)
        row.pack(fill=tk.X, pady=(0, 36))

        left = tk.Frame(row, bg=theme.BG_WINDOW)
        left.pack(side=tk.LEFT, fill=tk.X, expand=True)

        badge = widgets.IconBadge(left, icon, bg=theme.BG_WINDOW)
        badge.pack(side=tk.LEFT, anchor="n", padx=(0, 14))

        text_frame = tk.Frame(left, bg=theme.BG_WINDOW)
        text_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        title_label = tk.Label(
            text_frame, text=title, bg=theme.BG_WINDOW, fg=theme.FG_PRIMARY,
            font=theme.FONT_SECTION, anchor="w", justify=tk.LEFT,
        )
        title_label.pack(anchor="w")

        subtitle_label = tk.Label(
            text_frame, text=subtitle, bg=theme.BG_WINDOW, fg=theme.FG_SECONDARY,
            font=theme.FONT_SUBTITLE, anchor="w", justify=tk.LEFT, wraplength=subtitle_wrap,
        )
        subtitle_label.pack(anchor="w", pady=(4, 0))

        return row, badge, title_label, subtitle_label

    def _build_toggle_row(
        self,
        parent,
        icon: str,
        title_msgid: str,
        subtitle_msgid: str,
        variable: tk.BooleanVar,
        on_change: Callable[[], None],
    ) -> dict:
        """Builds a badge + title/subtitle + toggle-switch row."""
        row, badge, title_label, subtitle_label = self._build_row_icon_text(
            parent, icon, i18n._(title_msgid), i18n._(subtitle_msgid),
        )
        switch = widgets.ToggleSwitch(row, variable=variable, command=on_change, bg=theme.BG_WINDOW)
        switch.pack(side=tk.RIGHT, anchor="n", padx=(16, 0))
        return {
            "badge": badge, "title": title_label, "subtitle": subtitle_label, "switch": switch,
            "title_msgid": title_msgid, "subtitle_msgid": subtitle_msgid,
        }

    def _build_sound_mode_row(self, parent):
        """"Sound Mode" block: badge + label, "split button" selector on the right."""
        row, _badge, title_label, subtitle_label = self._build_row_icon_text(
            parent, "equalizer", i18n._("Sound Mode"), i18n._("Equalizer and acoustic engine"), subtitle_wrap=200,
        )
        self._sound_mode_title = title_label
        self._sound_mode_label = subtitle_label
        self._sound_mode_select = widgets.SplitSelect(
            row, values=[], command=self._on_sound_mode_change, bg=theme.BG_WINDOW, width=230,
        )
        self._sound_mode_select.pack(side=tk.RIGHT, anchor="n", padx=(16, 0))

    def _build_equalizer_row(self, parent):
        """Clickable "Equalizer" row (badge + title + active mode), no card background."""
        row, badge, title_label, subtitle_label = self._build_row_icon_text(
            parent, "equalizer", i18n._("Equalizer"), "", subtitle_wrap=280,
        )
        self._eq_row = row
        self._eq_nav_badge = badge
        self._eq_nav_title = title_label
        self._eq_nav_subtitle = subtitle_label
        self._bind_click_recursive(row, self._on_eq_row_click)
        self._set_row_cursor(row, "hand2")

    def _build_crystalvoice_row(self, parent):
        """Clickable "CrystalVoice" row (badge + title + subtitle), no card background."""
        row, badge, title_label, subtitle_label = self._build_row_icon_text(
            parent, "voice", i18n._("CrystalVoice"), i18n._("In-game voice optimization"), subtitle_wrap=280,
        )
        self._cv_row = row
        self._cv_nav_badge = badge
        self._cv_nav_title = title_label
        self._cv_nav_subtitle = subtitle_label
        self._bind_click_recursive(row, self._on_cv_row_click)
        self._set_row_cursor(row, "hand2")

    def _build_decoder_row(self, parent):
        """Clickable "Decoder" row (badge + title + active mode), no card background."""
        row, badge, title_label, subtitle_label = self._build_row_icon_text(
            parent, "decoder", i18n._("Decoder"), "", subtitle_wrap=280,
        )
        self._decoder_row = row
        self._decoder_nav_badge = badge
        self._decoder_nav_title = title_label
        self._decoder_nav_subtitle = subtitle_label
        self._bind_click_recursive(row, self._on_decoder_row_click)
        self._set_row_cursor(row, "hand2")

    def _bind_click_recursive(self, widget, handler) -> None:
        widget.bind("<Button-1>", handler)
        for child in widget.winfo_children():
            self._bind_click_recursive(child, handler)

    def _set_row_cursor(self, widget, cursor: str) -> None:
        try:
            widget.config(cursor=cursor)
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._set_row_cursor(child, cursor)

    def _on_eq_row_click(self, _event=None):
        if self._eq_enabled:
            self._show_eq_page()

    def _set_eq_nav_enabled(self, enabled: bool) -> None:
        self._eq_enabled = enabled
        self._eq_nav_badge.set_enabled(enabled)
        self._eq_nav_title.config(fg=theme.FG_PRIMARY if enabled else theme.FG_THUMB_DISABLED)
        self._eq_nav_subtitle.config(fg=theme.FG_SECONDARY if enabled else theme.FG_THUMB_DISABLED)
        self._set_row_cursor(self._eq_row, "hand2" if enabled else "arrow")

    def _on_cv_row_click(self, _event=None):
        if self._cv_enabled:
            self._show_cv_page()

    def _set_cv_nav_enabled(self, enabled: bool) -> None:
        self._cv_enabled = enabled
        self._cv_nav_badge.set_enabled(enabled)
        self._cv_nav_title.config(fg=theme.FG_PRIMARY if enabled else theme.FG_THUMB_DISABLED)
        self._cv_nav_subtitle.config(fg=theme.FG_SECONDARY if enabled else theme.FG_THUMB_DISABLED)
        self._set_row_cursor(self._cv_row, "hand2" if enabled else "arrow")

    def _on_decoder_row_click(self, _event=None):
        if self._decoder_enabled:
            self._show_decoder_page()

    def _set_decoder_nav_enabled(self, enabled: bool) -> None:
        self._decoder_enabled = enabled
        self._decoder_nav_badge.set_enabled(enabled)
        self._decoder_nav_title.config(fg=theme.FG_PRIMARY if enabled else theme.FG_THUMB_DISABLED)
        self._decoder_nav_subtitle.config(
            fg=theme.FG_SECONDARY if enabled else theme.FG_THUMB_DISABLED
        )
        self._set_row_cursor(self._decoder_row, "hand2" if enabled else "arrow")

    # ------------------------------------------------------------------
    # Sidebar navigation and system volume
    # ------------------------------------------------------------------

    def _on_sidebar_select(self, key: str) -> None:
        """Handles a click on an enabled sidebar entry.

        Only "Devices" and "Settings" exist so far; "Playback" and
        "Recording" are built disabled and never reach this method.
        """
        if key == "devices":
            self._show_main_page()
        elif key == "settings":
            self._show_settings_page()

    def _init_system_volume(self) -> None:
        """Fills the sidebar sliders and starts watching for outside changes."""
        if not system_volume.available():
            self._sidebar.set_output_enabled(False)
            self._sidebar.set_input_enabled(False)
            self._sidebar.set_output_volume(None)
            self._sidebar.set_input_volume(None)
            self._set_status("System volume control unavailable")
            return

        self._refresh_volumes()
        # The callback fires on the watcher's thread: hop back to Tk's.
        self._volume_watcher = system_volume.start_watch(
            lambda: self.after(0, self._refresh_volumes)
        )
        self.bind("<Destroy>", self._on_destroy, add="+")

    def _on_destroy(self, event=None) -> None:
        """Stops the volume watcher when the window itself goes away.

        ``<Destroy>`` also fires for every child widget, hence the identity
        check on the event's widget.
        """
        if event is not None and event.widget is not self:
            return
        system_volume.stop_watch(self._volume_watcher)
        self._volume_watcher = None

    def _refresh_volumes(self) -> None:
        """Re-reads both system volumes and pushes them to the sidebar.

        The reads are two subprocess calls, so they go to the shared worker
        like every other blocking operation; only the display update runs on
        the Tk thread. Called at startup, after a write, and on every change
        the watcher reports - which can be several a second while another
        application starts a stream.
        """
        def worker():
            readings = {
                kind: system_volume.get_volume(kind)
                for kind in (system_volume.OUTPUT, system_volume.INPUT)
            }
            self.after(0, lambda: self._show_volumes(readings))

        if self._controller is None:
            self._show_volumes({
                kind: system_volume.get_volume(kind)
                for kind in (system_volume.OUTPUT, system_volume.INPUT)
            })
        else:
            self._controller.submit(worker)

    def _show_volumes(self, readings: dict[str, Optional[tuple[int, bool]]]) -> None:
        """Applies volume readings to the sidebar (Tk thread).

        A slider the user is currently dragging keeps its position (the sidebar
        filters that out), and a volume that can't be read - typically a
        microphone with no software gain control on macOS - disables its
        slider.
        """
        for kind, show, enable in (
            (system_volume.OUTPUT, self._sidebar.set_output_volume, self._sidebar.set_output_enabled),
            (system_volume.INPUT, self._sidebar.set_input_volume, self._sidebar.set_input_enabled),
        ):
            reading = readings.get(kind)
            self._volume_readable[kind] = reading is not None
            show(None if reading is None else reading[0])
            if reading is None:
                enable(False)

    def _on_output_volume_change(self, percent: int) -> None:
        """Handles a release of the PC output slider."""
        self._apply_volume(system_volume.OUTPUT, percent, i18n._("Volume"))

    def _on_input_volume_change(self, percent: int) -> None:
        """Handles a release of the PC microphone slider."""
        self._apply_volume(system_volume.INPUT, percent, i18n._("Microphone"))

    def _apply_volume(self, kind: str, percent: int, label: str) -> None:
        """Writes a system volume on the shared worker thread.

        ``pactl``/``osascript`` are subprocesses: running them in the Tk
        callback would stutter the slider. The controller's worker already
        serializes one job at a time, which is exactly the ordering we want
        when several releases pile up.

        When the target device is the G8 itself, the write goes to the card's
        ALSA mixer, which knocks it out of Direct Mode if it is still settling
        after a re-enumeration (see ``alsa_fix.SETTLE_DELAY_S``). In that
        window the write is postponed rather than dropped: the user's move
        still lands, just a few seconds later.
        """
        if self._controller is None:
            return

        def worker():
            wait = self._settle_delay_before_write(kind)
            if wait > 0:
                self.after(int(wait * 1000), lambda: self._apply_volume(kind, percent, label))
                return
            ok = system_volume.set_volume(kind, percent)
            self.after(0, lambda: self._finish_volume_change(label, percent, ok))

        self._controller.submit(worker)

    def _settle_delay_before_write(self, kind: str) -> float:
        """Seconds to wait before writing ``kind``'s volume, 0 if it can go now."""
        if not system_volume.default_device_is_g8(kind):
            return 0.0
        age = alsa_fix.seconds_since_enumeration(VENDOR_ID, PRODUCT_ID)
        if age is None or age >= alsa_fix.SETTLE_DELAY_S:
            return 0.0
        # + 0.1 s of margin: coming back exactly on the threshold would race
        # the very condition we're avoiding.
        return alsa_fix.SETTLE_DELAY_S - age + 0.1

    def _finish_volume_change(self, label: str, percent: int, ok: bool) -> None:
        if ok:
            self._set_status("{label}: {percent}%", label=label, percent=percent)
        else:
            self._set_status("{label}: command failed (see console)", label=label)
        # Show what the system actually applied (it may clamp or round).
        self._refresh_volumes()

    def _set_volume_sliders_enabled(self, enabled: bool) -> None:
        """Enables/disables both sliders, never re-enabling an unreadable one."""
        self._sidebar.set_output_enabled(enabled and self._volume_readable[system_volume.OUTPUT])
        self._sidebar.set_input_enabled(enabled and self._volume_readable[system_volume.INPUT])

    def _on_language_change(self, index: int) -> None:
        """Handles a language-selector change; persists and re-renders everything in place."""
        if 0 <= index < len(self._lang_codes):
            i18n.set_language(self._lang_codes[index])

    def _retranslate(self, _lang: str) -> None:
        """Registered as an i18n listener: re-applies every static text in place."""
        self.title(i18n._("Sound Blaster G8 - Control"))
        self._back_button.set_text(i18n._("←  Back"))
        self._sidebar.retranslate()

        title_msgid, title_font = self._current_title
        self._title_label.config(text=i18n._(title_msgid), font=title_font)

        for key, row in self._toggle_rows.items():
            row["title"].config(text=i18n._(row["title_msgid"]))
            subtitle = i18n._(row["subtitle_msgid"])
            if key in self._unavailable:
                subtitle = f"{subtitle}\n{i18n._('(not implemented)')}"
            row["subtitle"].config(text=subtitle)

        self._sound_mode_title.config(text=i18n._("Sound Mode"))
        subtitle = i18n._("Equalizer and acoustic engine")
        if "sound_mode" in self._unavailable:
            subtitle = f"{subtitle}\n{i18n._('(not implemented)')}"
        self._sound_mode_label.config(text=subtitle)

        self._eq_nav_title.config(text=i18n._("Equalizer"))

        self._cv_nav_title.config(text=i18n._("CrystalVoice"))
        cv_subtitle = i18n._("In-game voice optimization")
        if "crystalvoice" in self._unavailable:
            cv_subtitle = f"{cv_subtitle}\n{i18n._('(not implemented)')}"
        self._cv_nav_subtitle.config(text=cv_subtitle)

        # Like the Equalizer row, the Decoder row's subtitle is its active
        # mode (refreshed below): unavailability is signalled by greying the
        # row out, not by an extra line of text.
        self._decoder_nav_title.config(text=i18n._("Decoder"))

        if self._controller is not None:
            modes = self._controller.list_sound_modes()
            self._sound_mode_slugs = [slug for slug, _label in modes]
            self._sound_mode_labels = [i18n.sound_mode_label(slug, label) for slug, label in modes]
            self._sound_mode_select.set_values(self._sound_mode_labels)
            self._select_sound_mode(self._controller.get_sound_mode())
            self._update_eq_button_label()
            self._update_decoder_row_label()

        if self._eq_panel is not None:
            self._eq_panel.retranslate()

        if self._cv_panel is not None:
            self._cv_panel.retranslate()

        if self._decoder_panel is not None:
            self._decoder_panel.retranslate()

        self._render_status()

    def _init_controller(self):
        """Initializes the controller and connects to the hardware."""
        from ..controller import get_controller
        self._controller = get_controller()
        self._switches = {
            "direct_mode": self._direct_toggle_switch,
            "scout_mode": self._scout_toggle_switch,
            "logo_led": self._led_toggle_switch,
            "energy_saving": self._energy_toggle_switch,
        }
        self._controller.add_listener("reconnecting", self._on_reconnecting)

        modes = self._controller.list_sound_modes()
        self._sound_mode_slugs = [slug for slug, _label in modes]
        self._sound_mode_labels = [i18n.sound_mode_label(slug, label) for slug, label in modes]
        self._sound_mode_select.set_values(self._sound_mode_labels)
        self._select_sound_mode(self._controller.get_sound_mode())
        self._update_eq_button_label()
        self._update_decoder_row_label()

        # The three secondary panels are built on first navigation (see
        # _ensure_eq_panel & co.), not here: they cost ~1.5 MB of widgets
        # for pages most launches never open.

        if self._controller.connect():
            info = self._controller.get_debug_info()
            self._set_status(
                "Connected to Sound Blaster G8 (interface {interface})",
                interface=info.get("interface_number"),
            )
            self._load_current_state()
        else:
            self._set_status("No hardware detected - commands will have no effect")

        self._apply_feature_availability()

    def _apply_feature_availability(self):
        """Greys out controls whose USB frame hasn't been reverse-engineered yet."""
        if not self._controller:
            return

        for feature in ("direct_mode", "scout_mode", "logo_led", "energy_saving"):
            if not self._controller.is_feature_supported(feature):
                self._unavailable.add(feature)
                row = self._toggle_rows[feature]
                row["switch"].set_enabled(False)
                row["badge"].set_enabled(False)
                row["title"].config(fg=theme.FG_SECONDARY)
                row["subtitle"].config(
                    text=f"{row['subtitle'].cget('text')}\n{i18n._('(not implemented)')}",
                    fg=theme.FG_SECONDARY,
                )

        if not self._controller.is_feature_supported("sound_mode"):
            self._unavailable.add("sound_mode")
            self._sound_mode_select.set_enabled(False)
            self._sound_mode_label.config(
                text=f"{self._sound_mode_label.cget('text')}\n{i18n._('(not implemented)')}"
            )

        if not self._controller.is_feature_supported("eq"):
            self._unavailable.add("eq")
            self._set_eq_nav_enabled(False)

        if not self._controller.is_feature_supported("crystalvoice"):
            self._unavailable.add("crystalvoice")
            self._set_cv_nav_enabled(False)

        if not self._controller.is_feature_supported("decoder"):
            self._unavailable.add("decoder")
            self._set_decoder_nav_enabled(False)

    def _load_current_state(self):
        """Loads the current state from the controller."""
        if not self._controller:
            return

        # Load the states
        self._direct_mode_var.set(self._controller.get_direct_mode())
        self._scout_mode_var.set(self._controller.get_scout_mode())
        self._logo_led_var.set(self._controller.get_logo_led())
        self._energy_saving_var.set(self._controller.get_energy_saving())
        self._select_sound_mode(self._controller.get_sound_mode())
        self._update_eq_button_label()
        self._update_decoder_row_label()

    def _select_sound_mode(self, slug: str) -> None:
        """Sets the SplitSelect to the given sound mode (without firing the event)."""
        if slug in self._sound_mode_slugs:
            self._sound_mode_select.set_index(self._sound_mode_slugs.index(slug))

    def _update_eq_button_label(self) -> None:
        """Refreshes the Equalizer row's subtitle with the active mode."""
        if not self._controller:
            return
        slug = self._controller.get_sound_mode()
        label = slug
        for mode_slug, mode_label in self._controller.list_sound_modes():
            if mode_slug == slug:
                label = i18n.sound_mode_label(mode_slug, mode_label)
                break
        self._eq_nav_subtitle.config(text=label)

    def _update_decoder_row_label(self) -> None:
        """Refreshes the Decoder row's subtitle with the active mode."""
        if not self._controller:
            return
        slug = self._controller.get_decoder_mode()
        label = slug
        for mode_slug, mode_label in self._controller.list_decoder_modes():
            if mode_slug == slug:
                label = i18n.decoder_mode_label(mode_slug, mode_label)
                break
        self._decoder_nav_subtitle.config(text=label)

    # ------------------------------------------------------------------
    # Navigation between pages (no floating window)
    # ------------------------------------------------------------------

    def _show_page(
        self,
        page: tk.Frame,
        title_msgid: str,
        title_font: tuple,
        sidebar_key: str = "devices",
        show_back: bool = True,
    ) -> None:
        """Shows one page of ``self._pages``, hiding the others.

        The back button is shown on every "Devices" sub-page (Equalizer,
        CrystalVoice, Decoder) but not on "Devices" itself nor on other
        top-level sidebar destinations (``show_back=False``, e.g. Settings),
        which are left by clicking another sidebar entry instead. The title
        is remembered as a msgid so ``_retranslate`` can re-render it in the
        new language without knowing which page is up.

        Deliberately does *not* resize the window: it's sized once, for all
        pages at once, by ``_fit_window_to_content`` at startup - switching
        pages must not change the window's size (the user can still resize
        it by hand, that's untouched).
        """
        for other in self._pages:
            if other is not page:
                other.pack_forget()

        self._sidebar.select(sidebar_key)

        if page is self._main_page or not show_back:
            self._back_button.place_forget()
        else:
            self._back_button.place(x=24, rely=0.5, anchor="w")

        self._current_title = (title_msgid, title_font)
        self._title_label.config(text=i18n._(title_msgid), font=title_font)
        page.pack(expand=True, fill=tk.BOTH)

    def _show_main_page(self):
        """Shows the main page (hides the back button)."""
        # The Decoder row's subtitle is the active mode: it may have been
        # changed on the Decoder page we're coming back from.
        self._update_decoder_row_label()
        self._show_page(self._main_page, "Sound Blaster G8", theme.FONT_TITLE)

    # The three panels are built eagerly in _setup_ui (not lazily on first
    # navigation anymore): _fit_window_to_content needs every page's real
    # content in place to size the window once, for good, at startup. Each
    # ``_ensure_*`` is idempotent, so calling them again on navigation (kept
    # below, in case a panel ever becomes lazy again) is a no-op.

    def _ensure_eq_panel(self):
        """Builds the Equalizer panel (no-op if already built)."""
        if self._eq_panel is None and self._controller is not None:
            self._eq_panel = EQPanel(
                self._eq_page, self._controller,
                status_callback=self._set_status,
            )
            self._eq_panel.pack(fill=tk.BOTH, expand=True)

    def _ensure_cv_panel(self):
        """Builds the CrystalVoice panel (no-op if already built)."""
        if self._cv_panel is None and self._controller is not None:
            self._cv_panel = CrystalVoicePanel(
                self._cv_page, self._controller,
                status_callback=self._set_status,
            )
            self._cv_panel.pack(fill=tk.BOTH, expand=True)

    def _ensure_decoder_panel(self):
        """Builds the Decoder panel (no-op if already built)."""
        if self._decoder_panel is None and self._controller is not None:
            self._decoder_panel = DecoderPanel(
                self._decoder_page, self._controller,
                status_callback=self._set_status,
            )
            self._decoder_panel.pack(fill=tk.BOTH, expand=True)

    def _show_eq_page(self):
        """Shows the Equalizer page (with a back button at the top left)."""
        self._ensure_eq_panel()
        self._show_page(self._eq_page, "Equalizer", theme.FONT_TITLE_EQ)
        self._prepare_eq_page_async()

    def _show_cv_page(self):
        """Shows the CrystalVoice page (with a back button at the top left)."""
        self._ensure_cv_panel()
        self._show_page(self._cv_page, "CrystalVoice", theme.FONT_TITLE_EQ)
        if self._cv_panel is not None:
            self._cv_panel.refresh()

    def _show_decoder_page(self):
        """Shows the Decoder page (with a back button at the top left)."""
        self._ensure_decoder_panel()
        self._show_page(self._decoder_page, "Decoder", theme.FONT_TITLE_EQ)
        if self._decoder_panel is not None:
            self._decoder_panel.refresh()

    def _show_settings_page(self):
        """Shows the Settings page (top-level sidebar destination, no back button)."""
        self._show_page(
            self._settings_page, "Settings", theme.FONT_TITLE_EQ,
            sidebar_key="settings", show_back=False,
        )

    def _prepare_eq_page_async(self):
        """Prepares the equalizer (enables + applies a flat state if needed).

        Native Creative app behavior: if no equalizer is already active
        (mode "Disabled"), applies a flat equalizer (10 bands + Preamp at
        0 dB) and enables it - otherwise band writes would be acknowledged
        by the card but remain inaudible. If a mode is already active, does
        nothing. Doesn't block the display: the sliders remain usable
        immediately.
        """
        if not self._controller:
            return

        def worker():
            try:
                ok = bool(self._controller.prepare_eq_page())
            except Exception as exc:  # pragma: no cover - depends on hardware
                self.after(0, lambda: self._set_status("Enabling equalizer: error ({error})", error=exc))
                return
            if ok:
                def on_success():
                    self._set_status("Equalizer enabled")
                    if self._eq_panel is not None:
                        self._eq_panel.refresh()
                self.after(0, on_success)

        self._controller.submit(worker)

    def _fit_window_to_content(self) -> None:
        """Sizes the window once so it fits the largest of all pages.

        Called only from ``_setup_ui``, after every page (including the
        Equalizer/CrystalVoice/Decoder panels, eagerly built for this) has
        its real content built. Each page is packed in turn just long enough
        to measure the window's resulting requested size - none of this is
        visible, since it all happens before the window is first mapped on
        screen - then the geometry is fixed to the largest width/height
        found. Unlike the old per-page ``_fit_window_to_page``, navigating
        between pages afterwards never resizes the window again; the window
        remains user-resizable (``resizable(True, True)``, set in __init__).
        """
        max_width = MIN_WINDOW_WIDTH
        max_height = 0
        for page in self._pages:
            page.pack(expand=True, fill=tk.BOTH)
            self.update_idletasks()
            max_width = max(max_width, self.winfo_reqwidth())
            max_height = max(max_height, self.winfo_reqheight())
            page.pack_forget()
        self.geometry(f"{max_width}x{max_height}")

    def _set_status(self, template: str, **kwargs) -> None:
        """Single choke point for status-bar text: stores (template, kwargs) so
        the message can be re-rendered in the current language on demand
        (e.g. after a language switch), then renders it now."""
        self._last_status = (template, kwargs)
        self._render_status()

    def _render_status(self) -> None:
        template, kwargs = self._last_status
        text = i18n._(template).format(**kwargs) if kwargs else i18n._(template)
        self._status_label.config(text=text)

    # ------------------------------------------------------------------
    # Toggles (run outside the GUI thread)
    # ------------------------------------------------------------------

    def _on_reconnecting(self, active: bool) -> None:
        """Relays the controller's ``reconnecting`` event (worker thread).

        Also locks the volume sliders for the duration: while the card
        re-enumerates, and for ``alsa_fix.SETTLE_DELAY_S`` afterwards, a mixer
        write would drop it out of Direct Mode.
        """
        if active:
            self.after(0, lambda: self._set_status("Direct Mode: reconnecting the device…"))
            self.after(0, self._lock_volume_sliders)
        else:
            self.after(0, lambda: self._set_status("Device reconnected"))
            self.after(0, self._unlock_volume_sliders_after_settle)

    def _lock_volume_sliders(self) -> None:
        if self._volume_reenable_job is not None:
            self.after_cancel(self._volume_reenable_job)
            self._volume_reenable_job = None
        self._set_volume_sliders_enabled(False)

    def _unlock_volume_sliders_after_settle(self) -> None:
        def unlock():
            self._volume_reenable_job = None
            self._set_volume_sliders_enabled(True)
            self._refresh_volumes()

        if self._volume_reenable_job is not None:
            self.after_cancel(self._volume_reenable_job)
        self._volume_reenable_job = self.after(int(alsa_fix.SETTLE_DELAY_S * 1000), unlock)

    def _handle_toggle(
        self,
        name: str,
        label: str,
        var: tk.BooleanVar,
        setter: Callable[[bool], bool],
        getter: Optional[Callable[[], bool]] = None,
    ):
        """Runs a toggle in a thread, then resynchronizes the display.

        The setter may block for several seconds (Direct Mode's USB reset):
        the switch is disabled during the operation and the result is
        applied on the Tk thread.
        """
        if not self._controller:
            return

        requested = var.get()
        switch = self._switches.get(name)
        if switch is not None:
            switch.set_enabled(False)
        self._set_status("{label}: sending command…", label=label)

        def worker():
            error: Optional[Exception] = None
            ok = False
            state: Optional[bool] = None
            try:
                ok = bool(setter(requested))
                if getter is not None:
                    # Re-read the real hardware state: after a USB reset,
                    # the card is the sole source of truth.
                    state = getter()
            except Exception as exc:  # pragma: no cover - depends on hardware
                error = exc
            self.after(0, lambda: self._finish_toggle(
                name, label, var, requested, ok, state, error
            ))

        self._controller.submit(worker)

    def _finish_toggle(
        self,
        name: str,
        label: str,
        var: tk.BooleanVar,
        requested: bool,
        ok: bool,
        state: Optional[bool],
        error: Optional[Exception],
    ):
        """End of a toggle: re-enables the switch and shows the real state."""
        switch = self._switches.get(name)
        if switch is not None and name not in self._unavailable:
            switch.set_enabled(True)

        # Displayed state: the hardware's if it could be re-read, otherwise
        # the requested one (success) or the previous one (failure).
        effective = state if state is not None else (requested if ok else not requested)
        var.set(effective)

        if error is not None:
            self._set_status("{label}: error ({error})", label=label, error=error)
        elif ok:
            self._set_status("{label} enabled" if effective else "{label} disabled", label=label)
        else:
            self._set_status("{label}: command failed (see console)", label=label)

    def _on_direct_mode_change(self):
        """Handles a Direct Mode change."""
        self._handle_toggle(
            "direct_mode", i18n._("Direct Mode"), self._direct_mode_var,
            lambda v: self._controller.set_direct_mode(v),
            getter=lambda: self._controller.get_direct_mode(),
        )

    def _on_scout_mode_change(self):
        """Handles a Scout Mode change."""
        self._handle_toggle(
            "scout_mode", i18n._("Scout Mode"), self._scout_mode_var,
            lambda v: self._controller.set_scout_mode(v),
            getter=lambda: self._controller.get_scout_mode(),
        )

    def _on_logo_led_change(self):
        """Handles a Logo LED change."""
        self._handle_toggle(
            "logo_led", i18n._("Logo LED"), self._logo_led_var,
            lambda v: self._controller.set_logo_led(v),
            getter=lambda: self._controller.get_logo_led(),
        )

    def _on_energy_saving_change(self):
        """Handles an Energy Saving change."""
        self._handle_toggle(
            "energy_saving", i18n._("Power Saving"), self._energy_saving_var,
            lambda v: self._controller.set_energy_saving(v),
            getter=lambda: self._controller.get_energy_saving(),
        )

    def _on_sound_mode_change(self, index: int):
        """Handles a sound-mode selection in the SplitSelect."""
        if not self._controller:
            return

        if index < 0 or index >= len(self._sound_mode_slugs):
            return
        slug = self._sound_mode_slugs[index]
        label = self._sound_mode_labels[index]

        self._sound_mode_select.set_enabled(False)
        self._set_status('Sound Mode "{label}": sending command…', label=label)

        def worker():
            error: Optional[Exception] = None
            ok = False
            try:
                ok = bool(self._controller.set_sound_mode(slug))
            except Exception as exc:  # pragma: no cover - depends on hardware
                error = exc
            self.after(0, lambda: self._finish_sound_mode_change(slug, label, ok, error))

        self._controller.submit(worker)

    def _finish_sound_mode_change(
        self,
        slug: str,
        label: str,
        ok: bool,
        error: Optional[Exception],
    ):
        """End of a sound-mode selection: re-enables the SplitSelect."""
        if "sound_mode" not in self._unavailable:
            self._sound_mode_select.set_enabled(True)

        # On failure, resynchronize the display with the controller's real state.
        self._select_sound_mode(self._controller.get_sound_mode())
        self._update_eq_button_label()
        if self._eq_panel is not None:
            self._eq_panel.refresh()

        if error is not None:
            self._set_status("Sound Mode: error ({error})", error=error)
        elif ok:
            self._set_status('Sound Mode "{label}" applied', label=label)
        else:
            self._set_status('Sound Mode "{label}": command failed (see console)', label=label)
