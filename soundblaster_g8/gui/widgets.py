"""Widgets Canvas façon mockup : interrupteur à bascule, slider, boutons pilule,
badges d'icônes et sélecteur « split button ».

Tkinter n'offre pas nativement de coins arrondis ni d'interrupteurs à
bascule : ces classes dessinent les formes du design (« Sound Blaster
G8.dc.html ») sur un ``tk.Canvas`` tout en gardant une API proche des widgets
standard (``tk.BooleanVar``/``tk.DoubleVar``, callbacks ``command``) pour
s'intégrer sans changer la logique métier des pages appelantes.
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
    """Dessine une icône simple (glyphe géométrique) dans la zone [x0,y0,x1,y1].

    Approximations Canvas des pictogrammes SVG du mockup (traits/formes de
    base) : suffisant à l'échelle d'un badge 36x36, sans dépendance externe.
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
    elif name == "reset":
        canvas.create_arc(
            x0 + w * 0.08, y0 + h * 0.08, x1 - w * 0.22, y1 - h * 0.08,
            start=25, extent=280, style=tk.ARC, outline=color, width=1.6,
        )
        ax, ay = x1 - w * 0.26, y0 + h * 0.12
        canvas.create_line(ax, ay, ax, ay + h * 0.3, fill=color, width=1.6, capstyle=tk.ROUND)
        canvas.create_line(ax, ay, ax - w * 0.3, ay, fill=color, width=1.6, capstyle=tk.ROUND)


class IconBadge(tk.Canvas):
    """Badge carré arrondi (fond sombre) contenant une petite icône centrée."""

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
    """Interrupteur à bascule façon pilule (piste + pastille glissante)."""

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
    """Slider horizontal façon mockup : piste fine + curseur rond.

    Le curseur suit la souris pendant le glissement (callback ``on_change``,
    utilisé pour l'affichage local) et n'appelle ``on_release`` qu'au
    relâchement, comme l'ancien ``ttk.Scale`` + ``<ButtonRelease-1>`` : c'est
    le point où la valeur est envoyée au matériel.
    """

    HEIGHT = 22
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
    ):
        super().__init__(parent, height=self.HEIGHT, width=width, highlightthickness=0, bg=bg, bd=0)
        self._variable = variable
        self._from = from_
        self._to = to
        self._step = step
        self._on_change = on_change
        self._on_release = on_release
        self._width = width

        self.bind("<Configure>", self._on_configure)
        self.bind("<Button-1>", self._on_drag)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release_evt)
        self._variable.trace_add("write", lambda *_args: self._redraw())
        self._redraw()

    def _on_configure(self, event: tk.Event) -> None:
        self._width = event.width
        self._redraw()

    def _value_to_x(self, value: float) -> float:
        span = self._to - self._from
        ratio = 0.0 if span == 0 else (value - self._from) / span
        usable = max(self._width - 2 * self.THUMB_R, 1)
        return self.THUMB_R + ratio * usable

    def _x_to_value(self, x: float) -> float:
        usable = max(self._width - 2 * self.THUMB_R, 1)
        ratio = min(1.0, max(0.0, (x - self.THUMB_R) / usable))
        raw = self._from + ratio * (self._to - self._from)
        stepped = round(raw / self._step) * self._step
        return min(self._to, max(self._from, stepped))

    def _on_drag(self, event: tk.Event) -> None:
        value = self._x_to_value(event.x)
        if value != self._variable.get():
            self._variable.set(value)
            if self._on_change is not None:
                self._on_change(value)

    def _on_release_evt(self, _event=None) -> None:
        if self._on_release is not None:
            self._on_release()

    def _redraw(self) -> None:
        self.delete("all")
        cy = self.HEIGHT / 2
        self.create_line(
            self.THUMB_R, cy, max(self._width - self.THUMB_R, self.THUMB_R), cy,
            fill=theme.SLIDER_TRACK, width=self.TRACK_H, capstyle=tk.ROUND,
        )
        x = self._value_to_x(self._variable.get())
        self.create_oval(
            x - self.THUMB_R, cy - self.THUMB_R, x + self.THUMB_R, cy + self.THUMB_R,
            fill=theme.FG_THUMB, outline="#1a1a1c",
        )


class RoundedButton(tk.Canvas):
    """Bouton pilule à fond uni et coins arrondis, avec icône optionnelle."""

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


class SplitSelect(tk.Canvas):
    """Sélecteur façon mockup : champ texte + bouton chevron bleu accolé.

    Remplace le ``ttk.Combobox`` du Mode Sonore : même sémantique
    (liste de libellés, sélection par index) mais rendu fidèle au design
    (piste sombre + capuchon bleu arrondi à droite). Le menu déroulant
    s'appuie sur ``tk.Menu`` (natif à la plateforme).
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
        self._menu = tk.Menu(
            self, tearoff=0, bg=theme.BG_CONTROL, fg=theme.FG_PRIMARY,
            activebackground=theme.ACCENT, activeforeground=theme.FG_PRIMARY, bd=0,
        )
        self._build_menu()

        self.bind("<Button-1>", self._open_menu)
        self.bind("<Configure>", self._on_configure)
        self._redraw()

    def _build_menu(self) -> None:
        self._menu.delete(0, "end")
        for i, label in enumerate(self._values):
            self._menu.add_command(label=label, command=lambda idx=i: self._select(idx))

    def _on_configure(self, event: tk.Event) -> None:
        self._width = event.width
        self._redraw()

    def _open_menu(self, _event: tk.Event) -> None:
        if not self._enabled or not self._values:
            return
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        try:
            self._menu.tk_popup(x, y)
        finally:
            self._menu.grab_release()

    def _select(self, index: int) -> None:
        self.set_index(index)
        if self._command is not None:
            self._command(index)

    def set_values(self, values: Sequence[str]) -> None:
        self._values = list(values)
        self._build_menu()
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
        # Le capuchon n'est arrondi qu'à droite : on aplatit son bord gauche.
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
