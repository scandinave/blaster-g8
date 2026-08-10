"""
MainWindow for the Sound Blaster G8 control application.
Dark-themed Tkinter interface (see ``theme.py``/``widgets.py``), matching the
"Sound Blaster G8.dc.html" design mockup (product photo, icon badges, "split
button" style sound-mode selector).

Hardware commands run in a worker thread: toggling Direct Mode triggers a USB
reset on the card and takes 2 to 4 seconds, which would freeze the window if
done in the Tk callback. The result is brought back to the GUI thread via
``self.after(0, ...)``.

The window holds four "pages" (main page / Equalizer page / CrystalVoice
page / Decoder page) in the same container, only one packed at a time (no
floating window): see ``_show_main_page``/``_show_eq_page``/``_show_cv_page``/
``_show_decoder_page``.
"""

import threading
import tkinter as tk
from pathlib import Path
from typing import Callable, Optional

from ..controller import SoundBlasterController
from . import i18n, theme, widgets
from .crystalvoice_panel import CrystalVoicePanel
from .decoder_panel import DecoderPanel
from .eq_panel import EQPanel

MIN_WINDOW_WIDTH = 640
ASSETS_DIR = Path(__file__).parent / "assets"

#: (feature key, icon glyph, title msgid, subtitle msgid) for the two
#: toggle rows on the main page.
TOGGLE_DEFS = [
    ("direct_mode", "direct", "Direct Mode", "No signal processing"),
    ("scout_mode", "scout", "Scout Mode", "In-game sound detection"),
]


class MainWindow(tk.Tk):
    """Main window of the Sound Blaster G8 application."""

    def __init__(self):
        """Initializes the main window."""
        super().__init__(baseName="blaster-g8", className="blaster-g8")

        i18n.load_saved_language()

        self.title(i18n._("Sound Blaster G8 - Control"))
        self.resizable(True, True)
        self._app_icon_image = tk.PhotoImage(file=str(ASSETS_DIR / "icon.png"))
        self.iconphoto(True, self._app_icon_image)

        # Controller singleton
        self._controller: Optional[SoundBlasterController] = None

        # Toggle state
        self._direct_mode_var = tk.BooleanVar(value=False)
        self._scout_mode_var = tk.BooleanVar(value=False)

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

        # Window setup
        self._setup_ui()

    def _setup_ui(self):
        """Sets up the UI: header, pages, status bar."""
        theme.apply_theme(self)

        self._setup_header()
        i18n.add_listener(self._retranslate)

        # Pages container: main_page and eq_page are siblings, only one is
        # packed at a time (see _show_main_page/_show_eq_page).
        self._pages_container = tk.Frame(self, bg=theme.BG_WINDOW)
        self._pages_container.pack(expand=True, fill=tk.BOTH)

        self._main_page = tk.Frame(self._pages_container, bg=theme.BG_WINDOW)
        self._eq_page = tk.Frame(self._pages_container, bg=theme.BG_WINDOW)
        self._cv_page = tk.Frame(self._pages_container, bg=theme.BG_WINDOW)
        self._decoder_page = tk.Frame(self._pages_container, bg=theme.BG_WINDOW)
        self._pages = (self._main_page, self._eq_page, self._cv_page, self._decoder_page)

        self._setup_main_page(self._main_page)
        # The panels need the controller: built in _init_controller.
        self._eq_panel: Optional[EQPanel] = None
        self._cv_panel: Optional[CrystalVoicePanel] = None
        self._decoder_panel: Optional[DecoderPanel] = None

        # Status bar (shared between both pages)
        status_bar = tk.Frame(self, bg=theme.BG_WINDOW)
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

        divider = tk.Frame(self, bg=theme.BORDER_CARD, height=1)
        divider.pack(fill=tk.X, side=tk.BOTTOM)

        self._show_main_page()

        # Controller initialization
        self._init_controller()

        self._fit_window_to_page()

    def _setup_header(self):
        """Shared header: back button (hidden on the main page) + title + language selector."""
        header = tk.Frame(self, bg=theme.BG_WINDOW, height=64)
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

    def _on_language_change(self, index: int) -> None:
        """Handles a language-selector change; persists and re-renders everything in place."""
        if 0 <= index < len(self._lang_codes):
            i18n.set_language(self._lang_codes[index])

    def _retranslate(self, _lang: str) -> None:
        """Registered as an i18n listener: re-applies every static text in place."""
        self.title(i18n._("Sound Blaster G8 - Control"))
        self._back_button.set_text(i18n._("←  Back"))

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
        }
        self._controller.add_listener("reconnecting", self._on_reconnecting)

        modes = self._controller.list_sound_modes()
        self._sound_mode_slugs = [slug for slug, _label in modes]
        self._sound_mode_labels = [i18n.sound_mode_label(slug, label) for slug, label in modes]
        self._sound_mode_select.set_values(self._sound_mode_labels)
        self._select_sound_mode(self._controller.get_sound_mode())
        self._update_eq_button_label()
        self._update_decoder_row_label()

        self._eq_panel = EQPanel(
            self._eq_page, self._controller,
            status_callback=self._set_status,
        )
        self._eq_panel.pack(fill=tk.BOTH, expand=True)

        self._cv_panel = CrystalVoicePanel(
            self._cv_page, self._controller,
            status_callback=self._set_status,
        )
        self._cv_panel.pack(fill=tk.BOTH, expand=True)

        self._decoder_panel = DecoderPanel(
            self._decoder_page, self._controller,
            status_callback=self._set_status,
        )
        self._decoder_panel.pack(fill=tk.BOTH, expand=True)

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

        for feature in ("direct_mode", "scout_mode"):
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

    def _show_page(self, page: tk.Frame, title_msgid: str, title_font: tuple) -> None:
        """Shows one page of ``self._pages``, hiding the others.

        The back button is shown on every page but the main one, and the
        title is remembered as a msgid so ``_retranslate`` can re-render it
        in the new language without knowing which page is up.
        """
        for other in self._pages:
            if other is not page:
                other.pack_forget()

        if page is self._main_page:
            self._back_button.place_forget()
        else:
            self._back_button.place(x=24, rely=0.5, anchor="w")

        self._current_title = (title_msgid, title_font)
        self._title_label.config(text=i18n._(title_msgid), font=title_font)
        page.pack(expand=True, fill=tk.BOTH)
        self._fit_window_to_page()

    def _show_main_page(self):
        """Shows the main page (hides the back button)."""
        # The Decoder row's subtitle is the active mode: it may have been
        # changed on the Decoder page we're coming back from.
        self._update_decoder_row_label()
        self._show_page(self._main_page, "Sound Blaster G8", theme.FONT_TITLE)

    def _show_eq_page(self):
        """Shows the Equalizer page (with a back button at the top left)."""
        self._show_page(self._eq_page, "Equalizer", theme.FONT_TITLE_EQ)
        self._prepare_eq_page_async()

    def _show_cv_page(self):
        """Shows the CrystalVoice page (with a back button at the top left)."""
        self._show_page(self._cv_page, "CrystalVoice", theme.FONT_TITLE_EQ)
        if self._cv_panel is not None:
            self._cv_panel.refresh()

    def _show_decoder_page(self):
        """Shows the Decoder page (with a back button at the top left)."""
        self._show_page(self._decoder_page, "Decoder", theme.FONT_TITLE_EQ)
        if self._decoder_panel is not None:
            self._decoder_panel.refresh()

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

        threading.Thread(target=worker, name="g8-eq-enable", daemon=True).start()

    def _fit_window_to_page(self):
        """Resizes the window so the displayed page fits entirely."""
        self.update_idletasks()
        width = max(MIN_WINDOW_WIDTH, self.winfo_reqwidth())
        height = self.winfo_reqheight()
        self.geometry(f"{width}x{height}")

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
        """Relays the controller's ``reconnecting`` event (worker thread)."""
        if active:
            self.after(0, lambda: self._set_status("Direct Mode: reconnecting the device…"))
        else:
            self.after(0, lambda: self._set_status("Device reconnected"))

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

        threading.Thread(target=worker, name=f"g8-{name}", daemon=True).start()

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

        threading.Thread(target=worker, name="g8-sound_mode", daemon=True).start()

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
