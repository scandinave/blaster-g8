"""Mockup-style Canvas widgets: toggle switch, slider, pill buttons,
icon badges, and a "split button" selector.

Tkinter has no native support for rounded corners or toggle switches: these
classes draw the design's shapes ("Sound Blaster G8.dc.html") on a
``tk.Canvas`` while keeping an API close to standard widgets
(``tk.BooleanVar``/``tk.DoubleVar``, ``command`` callbacks) so they drop in
without changing the calling pages' business logic.
"""

import tkinter as tk
import tkinter.font as tkfont
from typing import Callable, Optional, Sequence

from . import theme

ICON_COLOR = "#cfcfd2"
BADGE_BG = "#3d3d43"


def _rounded_rect_points(x1: float, y1: float, x2: float, y2: float, radius: float) -> list[float]:
    radius = max(0.0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    return [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]


def draw_rounded_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, radius: float, **kwargs):
    return canvas.create_polygon(
        _rounded_rect_points(x1, y1, x2, y2, radius), smooth=True, **kwargs
    )


def draw_icon(canvas: tk.Canvas, name: str, x0: float, y0: float, x1: float, y1: float, color: str = ICON_COLOR) -> None:
    """Draws a simple icon (geometric glyph) within the [x0,y0,x1,y1] area.

    Canvas approximations of the mockup's SVG pictograms (basic
    lines/shapes): good enough at 36x36 badge scale, with no external
    dependency.
    """
    w = x1 - x0
    h = y1 - y0
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2

    if name == "direct":
        canvas.create_line(x0, cy, x1, cy, fill=color, width=2, capstyle=tk.ROUND)
        r = w * 3 / 18
        canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=color, width=2)
    elif name == "scout":
        r = w * 7 / 18
        canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=color, width=1.6)
        r2 = w * 2 / 18
        canvas.create_oval(cx - r2, cy - r2, cx + r2, cy + r2, fill=color, outline="")
    elif name == "voice":
        head_r = w * 3 / 18
        head_cy = y0 + h * 6 / 18
        canvas.create_oval(cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r, fill=color, outline="")
        canvas.create_line(cx, y0 + h * 9 / 18, cx, y0 + h * 14 / 18, fill=color, width=1.6, capstyle=tk.ROUND)
        canvas.create_line(
            x0 + w * 5 / 18, y0 + h * 14 / 18, x0 + w * 13 / 18, y0 + h * 14 / 18,
            fill=color, width=1.6, capstyle=tk.ROUND,
        )
    elif name == "equalizer":
        bars = (
            (x0 + w * 1 / 16, y0 + h * 7 / 16, w * 3 / 16, h * 7 / 16),
            (x0 + w * 6.5 / 16, y0 + h * 3 / 16, w * 3 / 16, h * 11 / 16),
            (x0 + w * 12 / 16, y0 + h * 9 / 16, w * 3 / 16, h * 5 / 16),
        )
        for bx, by, bw, bh in bars:
            canvas.create_rectangle(bx, by, bx + bw, by + bh, fill=color, outline="")
    elif name == "decoder":
        # Speaker cone + two radiating arcs (Dolby decoder / DRC).
        canvas.create_polygon(
            x0 + w * 2 / 18, y0 + h * 7 / 18,
            x0 + w * 5 / 18, y0 + h * 7 / 18,
            x0 + w * 8 / 18, y0 + h * 3 / 18,
            x0 + w * 8 / 18, y0 + h * 15 / 18,
            x0 + w * 5 / 18, y0 + h * 11 / 18,
            x0 + w * 2 / 18, y0 + h * 11 / 18,
            fill=color, outline="",
        )
        for span in (5, 8):
            canvas.create_arc(
                cx - w * span / 18, cy - h * span / 18,
                cx + w * span / 18, cy + h * span / 18,
                start=-55, extent=110, style=tk.ARC, outline=color, width=1.6,
            )
    elif name == "reset":
        canvas.create_arc(
            x0 + w * 0.08, y0 + h * 0.08, x1 - w * 0.22, y1 - h * 0.08,
            start=25, extent=280, style=tk.ARC, outline=color, width=1.6,
        )
        ax, ay = x1 - w * 0.26, y0 + h * 0.12
        canvas.create_line(ax, ay, ax, ay + h * 0.3, fill=color, width=1.6, capstyle=tk.ROUND)
        canvas.create_line(ax, ay, ax - w * 0.3, ay, fill=color, width=1.6, capstyle=tk.ROUND)


class IconBadge(tk.Canvas):
    """Rounded square badge (dark background) with a small centered icon."""

    SIZE = 36

    def __init__(self, parent: tk.Misc, icon: str, bg: str = theme.BG_WINDOW, badge_bg: str = BADGE_BG, radius: int = 8):
        super().__init__(parent, width=self.SIZE, height=self.SIZE, highlightthickness=0, bg=bg, bd=0)
        self._icon = icon
        self._badge_bg = badge_bg
        self._radius = radius
        self._enabled = True
        self._redraw()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._redraw()

    def _redraw(self) -> None:
        self.delete("all")
        badge_bg = self._badge_bg if self._enabled else theme.BG_TRACK_DISABLED
        color = ICON_COLOR if self._enabled else theme.FG_THUMB_DISABLED
        draw_rounded_rect(self, 0, 0, self.SIZE, self.SIZE, self._radius, fill=badge_bg, outline="")
        pad = self.SIZE * 9 / 36
        draw_icon(self, self._icon, pad, pad, self.SIZE - pad, self.SIZE - pad, color=color)


class ToggleSwitch(tk.Canvas):
    """Pill-shaped toggle switch (track + sliding thumb)."""

    WIDTH = 38
    HEIGHT = 22
    PADDING = 2

    def __init__(
        self,
        parent: tk.Misc,
        variable: tk.BooleanVar,
        command: Optional[Callable[[], None]] = None,
        bg: str = theme.BG_WINDOW,
    ):
        super().__init__(
            parent, width=self.WIDTH, height=self.HEIGHT,
            highlightthickness=0, bg=bg, bd=0, cursor="hand2",
        )
        self._variable = variable
        self._command = command
        self._enabled = True
        self.bind("<Button-1>", self._on_click)
        self._variable.trace_add("write", lambda *_args: self._redraw())
        self._redraw()

    def _on_click(self, _event=None) -> None:
        if not self._enabled:
            return
        self._variable.set(not self._variable.get())
        if self._command is not None:
            self._command()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.config(cursor="hand2" if enabled else "arrow")
        self._redraw()

    def _redraw(self) -> None:
        self.delete("all")
        on = bool(self._variable.get())
        if not self._enabled:
            track, thumb = theme.BG_TRACK_DISABLED, theme.FG_THUMB_DISABLED
        elif on:
            track, thumb = theme.ACCENT, theme.FG_THUMB
        else:
            track, thumb = theme.BG_CONTROL, theme.FG_THUMB

        radius = self.HEIGHT / 2
        draw_rounded_rect(
            self, 1, 1, self.WIDTH - 1, self.HEIGHT - 1, radius, fill=track, outline="",
        )
        thumb_r = (self.HEIGHT - 2 * self.PADDING) / 2
        cy = self.HEIGHT / 2
        cx = self.WIDTH - radius if on else radius
        self.create_oval(
            cx - thumb_r, cy - thumb_r, cx + thumb_r, cy + thumb_r,
            fill=thumb, outline="",
        )


class Slider(tk.Canvas):
    """Mockup-style slider: thin track + round thumb, horizontal or vertical.

    The thumb follows the mouse while dragging (``on_change`` callback, used
    for local display) and only calls ``on_release`` on release, like the
    old ``ttk.Scale`` + ``<ButtonRelease-1>``: that's the point where the
    value is sent to the hardware.

    In vertical orientation, the thumb moves along the Y axis: the top of
    the track corresponds to ``to`` (max value), like a physical fader - so
    the Tk axis (Y increasing downward) is inverted.
    """

    THICKNESS = 22  # track thickness (height when horizontal, width when vertical)
    TRACK_H = 4
    THUMB_R = 9

    def __init__(
        self,
        parent: tk.Misc,
        variable: tk.DoubleVar,
        from_: float,
        to: float,
        step: float = 0.5,
        on_change: Optional[Callable[[float], None]] = None,
        on_release: Optional[Callable[[], None]] = None,
        bg: str = theme.BG_CARD,
        width: int = 220,
        height: int = 180,
        orientation: str = "horizontal",
    ):
        self._orientation = orientation
        self._vertical = orientation == "vertical"
        # ``_length``: dimension along the drag axis (width when horizontal,
        # height when vertical); the perpendicular thickness is always
        # THICKNESS.
        self._length = height if self._vertical else width
        canvas_w = self.THICKNESS if self._vertical else width
        canvas_h = height if self._vertical else self.THICKNESS
        super().__init__(parent, width=canvas_w, height=canvas_h, highlightthickness=0, bg=bg, bd=0)
        self._variable = variable
        self._from = from_
        self._to = to
        self._step = step
        self._on_change = on_change
        self._on_release = on_release

        self.bind("<Configure>", self._on_configure)
        self.bind("<Button-1>", self._on_drag)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release_evt)
        self._variable.trace_add("write", lambda *_args: self._redraw())
        self._redraw()

    def _on_configure(self, event: tk.Event) -> None:
        self._length = event.height if self._vertical else event.width
        self._redraw()

    def _value_to_pos(self, value: float) -> float:
        span = self._to - self._from
        ratio = 0.0 if span == 0 else (value - self._from) / span
        usable = max(self._length - 2 * self.THUMB_R, 1)
        pos = self.THUMB_R + ratio * usable
        # Inverted Y axis: high value = top position (smaller Y).
        return self._length - pos if self._vertical else pos

    def _pos_to_value(self, pos: float) -> float:
        if self._vertical:
            pos = self._length - pos
        usable = max(self._length - 2 * self.THUMB_R, 1)
        ratio = min(1.0, max(0.0, (pos - self.THUMB_R) / usable))
        raw = self._from + ratio * (self._to - self._from)
        stepped = round(raw / self._step) * self._step
        return min(self._to, max(self._from, stepped))

    def _on_drag(self, event: tk.Event) -> None:
        value = self._pos_to_value(event.y if self._vertical else event.x)
        if value != self._variable.get():
            self._variable.set(value)
            if self._on_change is not None:
                self._on_change(value)

    def _on_release_evt(self, _event=None) -> None:
        if self._on_release is not None:
            self._on_release()

    def _redraw(self) -> None:
        self.delete("all")
        c = self.THICKNESS / 2
        pos = self._value_to_pos(self._variable.get())
        track_end = max(self._length - self.THUMB_R, self.THUMB_R)
        if self._vertical:
            self.create_line(
                c, self.THUMB_R, c, track_end,
                fill=theme.SLIDER_TRACK, width=self.TRACK_H, capstyle=tk.ROUND,
            )
            self.create_oval(
                c - self.THUMB_R, pos - self.THUMB_R, c + self.THUMB_R, pos + self.THUMB_R,
                fill=theme.FG_THUMB, outline="#1a1a1c",
            )
        else:
            self.create_line(
                self.THUMB_R, c, track_end, c,
                fill=theme.SLIDER_TRACK, width=self.TRACK_H, capstyle=tk.ROUND,
            )
            self.create_oval(
                pos - self.THUMB_R, c - self.THUMB_R, pos + self.THUMB_R, c + self.THUMB_R,
                fill=theme.FG_THUMB, outline="#1a1a1c",
            )


class RoundedButton(tk.Canvas):
    """Pill button with a solid fill and rounded corners, with optional icon."""

    def __init__(
        self,
        parent: tk.Misc,
        text: str,
        command: Optional[Callable[[], None]] = None,
        icon: Optional[str] = None,
        bg: str = theme.BG_WINDOW,
        fill: str = theme.BG_CONTROL,
        fg: str = theme.FG_PRIMARY,
        font=theme.FONT_BUTTON,
        radius: int = 6,
        padx: int = 16,
        pady: int = 10,
        icon_size: int = 15,
        icon_gap: int = 10,
    ):
        super().__init__(parent, highlightthickness=0, bg=bg, bd=0, cursor="hand2")
        self._command = command
        self._fill = fill
        self._fg = fg
        self._text = text
        self._font = font
        self._radius = radius
        self._padx = padx
        self._pady = pady
        self._icon = icon
        self._icon_size = icon_size
        self._icon_gap = icon_gap
        self._enabled = True

        self.bind("<Button-1>", self._on_click)
        self._resize_to_text()
        self._redraw()

    def _resize_to_text(self) -> None:
        f = tkfont.Font(font=self._font)
        text_w = f.measure(self._text)
        icon_w = (self._icon_size + self._icon_gap) if self._icon else 0
        width = text_w + icon_w + 2 * self._padx
        height = max(f.metrics("linespace"), self._icon_size) + 2 * self._pady
        self.config(width=width, height=height)

    def _on_click(self, _event=None) -> None:
        if self._enabled and self._command is not None:
            self._command()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.config(cursor="hand2" if enabled else "arrow")
        self._redraw()

    def set_text(self, text: str) -> None:
        self._text = text
        self._resize_to_text()
        self._redraw()

    def set_fill(self, fill: str) -> None:
        """Changes the button's background (used to mark a selected choice)."""
        self._fill = fill
        self._redraw()

    def _redraw(self) -> None:
        self.delete("all")
        width = int(self["width"])
        height = int(self["height"])
        fill = self._fill if self._enabled else theme.BG_TRACK_DISABLED
        fg = self._fg if self._enabled else theme.FG_THUMB_DISABLED
        draw_rounded_rect(self, 0, 0, width, height, self._radius, fill=fill, outline="")

        if self._icon:
            f = tkfont.Font(font=self._font)
            text_w = f.measure(self._text)
            content_w = self._icon_size + self._icon_gap + text_w
            start_x = (width - content_w) / 2
            icon_y0 = (height - self._icon_size) / 2
            draw_icon(self, self._icon, start_x, icon_y0, start_x + self._icon_size, icon_y0 + self._icon_size, color=fg)
            text_x = start_x + self._icon_size + self._icon_gap
            self.create_text(text_x, height / 2, text=self._text, fill=fg, font=self._font, anchor="w")
        else:
            self.create_text(width / 2, height / 2, text=self._text, fill=fg, font=self._font)


class _DropdownPopup:
    """Scrollable dropdown for ``SplitSelect``: a borderless ``Toplevel``
    with a ``Canvas``+``Scrollbar`` list, built fresh on every ``open()``
    and fully destroyed on ``close()`` - no widget reuse across opens, so
    nothing can leak.
    """

    ROW_HEIGHT = 32
    MAX_VISIBLE_ROWS = 8
    SCROLLBAR_W = 16
    MAX_POPUP_W = 420

    def __init__(self, owner: "SplitSelect"):
        self._owner = owner
        self._toplevel: Optional[tk.Toplevel] = None
        self._canvas: Optional[tk.Canvas] = None
        self._row_frames: list[tk.Frame] = []
        self._row_labels: list[tk.Label] = []
        self._active_index: int = -1
        self._root_click_id: Optional[str] = None

    def is_open(self) -> bool:
        return self._toplevel is not None

    def toggle(self) -> None:
        self.close() if self.is_open() else self.open()

    def open(self) -> None:
        owner = self._owner
        values = owner._values
        if not values:
            return
        self.close()  # defensive, should already be closed

        n = len(values)
        visible = min(n, self.MAX_VISIBLE_ROWS)
        show_scrollbar = n > self.MAX_VISIBLE_ROWS
        content_w = min(
            self.MAX_POPUP_W,
            max(owner._width, SplitSelect.compute_width(values, font=owner._font, min_width=owner._width)),
        )
        if show_scrollbar:
            content_w -= self.SCROLLBAR_W
        content_h = visible * self.ROW_HEIGHT

        top = tk.Toplevel(owner)
        top.withdraw()
        top.overrideredirect(True)
        top.transient(owner.winfo_toplevel())
        top.configure(bg=theme.BORDER_CARD)

        frame = tk.Frame(top, bg=theme.BORDER_CARD, bd=1)
        frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(frame, width=content_w, height=content_h, bg=theme.BG_CONTROL, highlightthickness=0, bd=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        if show_scrollbar:
            sb = tk.Scrollbar(frame, orient="vertical", command=canvas.yview)
            sb.grid(row=0, column=1, sticky="ns")
            canvas.configure(yscrollcommand=sb.set)
        canvas.configure(yscrollincrement=self.ROW_HEIGHT)

        inner = tk.Frame(canvas, bg=theme.BG_CONTROL)
        canvas.create_window((0, 0), window=inner, anchor="nw", width=content_w)

        self._row_frames, self._row_labels = [], []
        for i, label_text in enumerate(values):
            rf = tk.Frame(inner, bg=theme.BG_CONTROL, height=self.ROW_HEIGHT)
            rf.pack(fill="x")
            rf.pack_propagate(False)
            lbl = tk.Label(
                rf, text=label_text, bg=theme.BG_CONTROL, fg=theme.FG_PRIMARY, font=owner._font, anchor="w", padx=12,
            )
            lbl.pack(fill="both", expand=True)
            lbl.bind("<Enter>", lambda e, idx=i: self._set_active(idx))
            lbl.bind("<Leave>", lambda e, idx=i: self._clear_active(idx))
            lbl.bind("<Button-1>", lambda e, idx=i: self._pick(idx))
            self._row_frames.append(rf)
            self._row_labels.append(lbl)

        inner.update_idletasks()
        canvas.configure(scrollregion=(0, 0, content_w, n * self.ROW_HEIGHT))

        # Position under the field; flip above if it would overflow the
        # bottom of the screen, clamp horizontally to stay on-screen.
        x = owner.winfo_rootx()
        y = owner.winfo_rooty() + owner.winfo_height()
        total_h = content_h + 2  # + 1px border each side
        screen_h, screen_w = owner.winfo_screenheight(), owner.winfo_screenwidth()
        if y + total_h > screen_h and owner.winfo_rooty() - total_h >= 0:
            y = owner.winfo_rooty() - total_h
        x = max(0, min(x, screen_w - content_w))
        popup_total_w = content_w + (self.SCROLLBAR_W if show_scrollbar else 0) + 2
        top.geometry(f"{popup_total_w}x{total_h}+{x}+{y}")
        top.deiconify()
        top.lift()
        top.focus_set()

        top.bind("<Escape>", lambda e: self.close())
        top.bind("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
        top.bind("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))
        top.bind("<MouseWheel>", lambda e: canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        top.bind("<Up>", lambda e: self._move_active(-1))
        top.bind("<Down>", lambda e: self._move_active(1))
        top.bind("<Return>", lambda e: self._pick(self._active_index))

        # Click-outside-to-close: bound on the containing toplevel (not
        # bind_all, which would clobber other code's app-wide bindings on
        # unbind). Every descendant widget's bindtags include its
        # containing toplevel, so any Button-1 elsewhere in the window
        # bubbles up here regardless of window manager. Deferred to the
        # next idle tick: binding it synchronously here would let the very
        # click that opened the popup also reach this handler within the
        # same event dispatch (widget tag -> ... -> toplevel tag), closing
        # the popup it just opened.
        root = owner.winfo_toplevel()
        root.after_idle(self._bind_root_click, root)

        self._toplevel, self._canvas = top, canvas
        self._active_index = -1
        if 0 <= owner._index < n:
            self._set_active(owner._index)
            self._scroll_into_view(owner._index)

    def _bind_root_click(self, root: tk.Misc) -> None:
        if not self.is_open():
            return  # closed again before the deferred bind ran
        self._root_click_id = root.bind("<Button-1>", self._on_root_click, add="+")

    def close(self) -> None:
        if self._toplevel is None:
            return
        if self._root_click_id is not None:
            self._owner.winfo_toplevel().unbind("<Button-1>", self._root_click_id)
            self._root_click_id = None
        self._toplevel.destroy()
        self._toplevel = self._canvas = None
        self._row_frames, self._row_labels = [], []
        self._active_index = -1

    def _on_root_click(self, _event) -> None:
        # Fires after any widget-specific handler (e.g. SplitSelect's own
        # Button-1 toggle), so by the time we get here the popup is either
        # already legitimately re-opened/closed or this really is an
        # "outside" click.
        if self.is_open():
            self.close()

    def _set_active(self, idx: int) -> None:
        self._clear_active(self._active_index)
        self._active_index = idx
        if 0 <= idx < len(self._row_labels):
            self._row_frames[idx].configure(bg=theme.ACCENT)
            self._row_labels[idx].configure(bg=theme.ACCENT)

    def _clear_active(self, idx: int) -> None:
        if 0 <= idx < len(self._row_labels):
            self._row_frames[idx].configure(bg=theme.BG_CONTROL)
            self._row_labels[idx].configure(bg=theme.BG_CONTROL)

    def _move_active(self, delta: int) -> None:
        n = len(self._row_labels)
        if n == 0:
            return
        new_idx = max(0, min(n - 1, (self._active_index if self._active_index >= 0 else 0) + delta))
        self._set_active(new_idx)
        self._scroll_into_view(new_idx)

    def _scroll_into_view(self, idx: int) -> None:
        canvas = self._canvas
        total_h = len(self._row_labels) * self.ROW_HEIGHT
        view_h = canvas.winfo_height()
        row_top, row_bottom = idx * self.ROW_HEIGHT, (idx + 1) * self.ROW_HEIGHT
        view_top = canvas.canvasy(0)
        if row_top < view_top:
            canvas.yview_moveto(row_top / total_h)
        elif row_bottom > view_top + view_h:
            canvas.yview_moveto((row_bottom - view_h) / total_h)

    def _pick(self, idx: int) -> None:
        if idx < 0:
            return
        self._owner._select(idx)
        self.close()


class SplitSelect(tk.Canvas):
    """Mockup-style selector: text field + attached blue chevron button.

    Replaces the Sound Mode's ``ttk.Combobox``: same semantics (list of
    labels, selection by index) but rendered to match the design (dark
    track + rounded blue cap on the right). The dropdown is a custom
    scrollable popup (see ``_DropdownPopup``), since ``tk.Menu`` has no
    scrolling support and long lists (e.g. the 51 sound modes) would
    otherwise overflow the screen.
    """

    HEIGHT = 44
    ARROW_W = 44

    def __init__(
        self,
        parent: tk.Misc,
        values: Sequence[str],
        command: Optional[Callable[[int], None]] = None,
        bg: str = theme.BG_WINDOW,
        width: int = 230,
        font=theme.FONT_SMALL,
    ):
        super().__init__(parent, width=width, height=self.HEIGHT, highlightthickness=0, bg=bg, bd=0, cursor="hand2")
        self._values = list(values)
        self._command = command
        self._width = width
        self._index = 0 if self._values else -1
        self._font = font
        self._enabled = True
        self._popup = _DropdownPopup(self)

        self.bind("<Button-1>", self._open_dropdown)
        self.bind("<Configure>", self._on_configure)
        self.bind("<Destroy>", lambda e: self._popup.close())
        self._redraw()

    @classmethod
    def compute_width(cls, values: Sequence[str], font=theme.FONT_SMALL, min_width: int = 90, slack: int = 8) -> int:
        """Minimum width (px) that won't truncate any of ``values`` under
        ``_redraw``'s ellipsis logic, i.e. ``width - ARROW_W - 24 >=
        measure(label)`` for every label."""
        f = tkfont.Font(font=font)
        max_text_w = max((f.measure(v) for v in values), default=0)
        return max(min_width, max_text_w + cls.ARROW_W + 24 + slack)

    def _on_configure(self, event: tk.Event) -> None:
        self._width = event.width
        self._redraw()

    def _open_dropdown(self, _event: tk.Event) -> None:
        if not self._enabled or not self._values:
            return
        self._popup.toggle()

    def _select(self, index: int) -> None:
        self.set_index(index)
        if self._command is not None:
            self._command(index)

    def set_values(self, values: Sequence[str]) -> None:
        self._popup.close()
        self._values = list(values)
        if self._index >= len(self._values):
            self._index = len(self._values) - 1
        self._redraw()

    def set_index(self, index: int) -> None:
        if 0 <= index < len(self._values):
            self._index = index
            self._redraw()

    def get_index(self) -> int:
        return self._index

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        if not enabled:
            self._popup.close()
        self.config(cursor="hand2" if enabled else "arrow")
        self._redraw()

    def _redraw(self) -> None:
        self.delete("all")
        radius = 6
        fill = theme.BG_CONTROL if self._enabled else theme.BG_TRACK_DISABLED
        accent = theme.ACCENT if self._enabled else theme.BG_TRACK_DISABLED
        fg = theme.FG_PRIMARY if self._enabled else theme.FG_THUMB_DISABLED

        draw_rounded_rect(self, 0, 0, self._width, self.HEIGHT, radius, fill=fill, outline="")

        arrow_x0 = self._width - self.ARROW_W
        draw_rounded_rect(self, arrow_x0, 0, self._width, self.HEIGHT, radius, fill=accent, outline="")
        # The cap is only rounded on the right: flatten its left edge.
        self.create_rectangle(arrow_x0, 0, arrow_x0 + radius, self.HEIGHT, fill=accent, outline="")

        label = self._values[self._index] if 0 <= self._index < len(self._values) else ""
        f = tkfont.Font(font=self._font)
        max_text_w = arrow_x0 - 24
        while f.measure(label) > max_text_w and len(label) > 1:
            label = label[:-1]
        if label != (self._values[self._index] if 0 <= self._index < len(self._values) else ""):
            label = label.rstrip() + "…"
        self.create_text(12, self.HEIGHT / 2, text=label, fill=fg, font=self._font, anchor="w")

        cx = arrow_x0 + self.ARROW_W / 2
        cy = self.HEIGHT / 2
        self.create_line(
            cx - 4, cy - 2, cx, cy + 2, cx + 4, cy - 2,
            fill="white", width=2, joinstyle=tk.ROUND, capstyle=tk.ROUND,
        )
