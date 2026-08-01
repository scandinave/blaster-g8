"""Thème sombre (couleurs, polices, styles ttk) pour l'interface Sound Blaster G8.

Palette et typographie reprises du mockup de design (claude.ai/design,
« Sound Blaster G8.dc.html ») : fond anthracite, accent bleu sur les
interrupteurs actifs, cartes légèrement plus claires pour l'égaliseur.
"""

import tkinter as tk
from tkinter import ttk

BG_WINDOW = "#2a2a2d"
BG_CARD = "#333338"
BORDER_CARD = "#45454b"
BG_CONTROL = "#57575f"
BG_VALUE = "#1e1e21"
BG_TRACK_DISABLED = "#4a4a50"

FG_PRIMARY = "#e4e4e6"
FG_SECONDARY = "#9a9aa0"
FG_LABEL = "#c8c8cc"
FG_STATUSBAR = "#b4b4b8"
FG_THUMB = "#f2f2f4"
FG_THUMB_DISABLED = "#8a8a90"

ACCENT = "#2f6fed"
SLIDER_TRACK = "#55555c"

FONT_FAMILY = "Segoe UI"

FONT_TITLE = (FONT_FAMILY, 18, "bold")
FONT_TITLE_EQ = (FONT_FAMILY, 15, "bold")
FONT_SECTION = (FONT_FAMILY, 12, "bold")
FONT_SUBTITLE = (FONT_FAMILY, 10)
FONT_LABEL = (FONT_FAMILY, 10)
FONT_BODY = (FONT_FAMILY, 11)
FONT_SMALL = (FONT_FAMILY, 10)
FONT_BUTTON = (FONT_FAMILY, 10, "bold")


def apply_theme(root: tk.Misc) -> None:
    """Configure le thème sombre global : fond de fenêtre + styles ttk."""
    root.configure(bg=BG_WINDOW)

    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(
        "Dark.TCombobox",
        fieldbackground=BG_CONTROL,
        background=BG_CONTROL,
        foreground=FG_PRIMARY,
        arrowcolor=FG_PRIMARY,
        bordercolor=BG_CONTROL,
        lightcolor=BG_CONTROL,
        darkcolor=BG_CONTROL,
        borderwidth=0,
        relief="flat",
        padding=8,
    )
    style.map(
        "Dark.TCombobox",
        fieldbackground=[("readonly", BG_CONTROL), ("disabled", BG_TRACK_DISABLED)],
        foreground=[("disabled", FG_THUMB_DISABLED)],
        background=[("readonly", BG_CONTROL), ("disabled", BG_TRACK_DISABLED)],
        selectbackground=[("readonly", BG_CONTROL)],
        selectforeground=[("readonly", FG_PRIMARY)],
    )

    root.option_add("*TCombobox*Listbox.background", BG_CONTROL)
    root.option_add("*TCombobox*Listbox.foreground", FG_PRIMARY)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", FG_PRIMARY)
    root.option_add("*TCombobox*Listbox.font", FONT_BODY)
