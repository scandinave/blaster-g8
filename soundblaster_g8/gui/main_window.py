"""
MainWindow pour l'application de contrôle Sound Blaster G8.
Interface Tkinter thème sombre (voir ``theme.py``/``widgets.py``), conforme
au mockup de design « Sound Blaster G8.dc.html » (photo produit, badges
d'icônes, sélecteur de mode sonore façon « split button »).

Les commandes matérielles sont exécutées dans un thread de travail : une
bascule du Direct Mode provoque un reset USB de la carte et prend 2 à 4
secondes, ce qui gèlerait la fenêtre si elle était faite dans le callback Tk.
Le résultat est rapatrié dans le thread graphique via ``self.after(0, ...)``.

La fenêtre contient deux « pages » (page principale / page Égaliseur) dans un
même conteneur, une seule visible à la fois (pas de fenêtre flottante) : voir
``_show_main_page``/``_show_eq_page``.
"""

import threading
import tkinter as tk
from pathlib import Path
from typing import Callable, Optional

from ..controller import SoundBlasterController
from . import theme, widgets
from .eq_panel import EQPanel

MIN_WINDOW_WIDTH = 640
ASSETS_DIR = Path(__file__).parent / "assets"


class MainWindow(tk.Tk):
    """Fenêtre principale de l'application Sound Blaster G8."""

    def __init__(self):
        """Initialise la fenêtre principale."""
        super().__init__()

        self.title("Sound Blaster G8 - Control")
        self.resizable(True, True)

        # Controller singleton
        self._controller: Optional[SoundBlasterController] = None

        # État des toggles
        self._direct_mode_var = tk.BooleanVar(value=False)
        self._scout_mode_var = tk.BooleanVar(value=False)
        self._crystalvoice_var = tk.BooleanVar(value=False)

        # Mode sonore : listes parallèles (slugs/labels) pilotant le SplitSelect.
        self._sound_mode_slugs: list[str] = []
        self._sound_mode_labels: list[str] = []

        # Interrupteurs indisponibles (fonction non reversée) : ils ne doivent
        # pas être réactivés à la fin d'une commande.
        self._unavailable: set[str] = set()
        self._switches: dict[str, widgets.ToggleSwitch] = {}
        self._toggle_rows: dict[str, dict] = {}
        self._eq_enabled = True

        # Configuration de la fenêtre
        self._setup_ui()

    def _setup_ui(self):
        """Configure l'interface utilisateur : en-tête, pages, barre de statut."""
        theme.apply_theme(self)

        self._setup_header()

        # Conteneur des pages : main_page et eq_page sont frères, une seule
        # est empaquetée à la fois (voir _show_main_page/_show_eq_page).
        self._pages_container = tk.Frame(self, bg=theme.BG_WINDOW)
        self._pages_container.pack(expand=True, fill=tk.BOTH)

        self._main_page = tk.Frame(self._pages_container, bg=theme.BG_WINDOW)
        self._eq_page = tk.Frame(self._pages_container, bg=theme.BG_WINDOW)

        self._setup_main_page(self._main_page)
        # L'EQPanel a besoin du contrôleur : construit dans _init_controller.
        self._eq_panel: Optional[EQPanel] = None

        # Status bar (partagée entre les deux pages)
        status_bar = tk.Frame(self, bg=theme.BG_WINDOW)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self._status_label = tk.Label(
            status_bar,
            text="Prêt",
            anchor=tk.W,
            bg=theme.BG_WINDOW,
            fg=theme.FG_STATUSBAR,
            font=theme.FONT_SMALL,
            padx=24,
            pady=10,
        )
        self._status_label.pack(expand=True, fill=tk.X)

        divider = tk.Frame(self, bg=theme.BORDER_CARD, height=1)
        divider.pack(fill=tk.X, side=tk.BOTTOM)

        self._show_main_page()

        # Initialisation du controller
        self._init_controller()

        self._fit_window_to_page()

    def _setup_header(self):
        """En-tête commun : bouton retour (masqué sur la page principale) + titre."""
        header = tk.Frame(self, bg=theme.BG_WINDOW, height=64)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        self._back_button = widgets.RoundedButton(
            header,
            text="←  Retour",
            command=self._show_main_page,
            bg=theme.BG_WINDOW,
            fill=theme.BG_CONTROL,
            fg=theme.FG_PRIMARY,
            font=theme.FONT_BUTTON,
            padx=16,
            pady=8,
        )
        # Placé/masqué dynamiquement par _show_main_page/_show_eq_page.

        self._title_label = tk.Label(
            header,
            text="Sound Blaster G8",
            bg=theme.BG_WINDOW,
            fg=theme.FG_PRIMARY,
            font=theme.FONT_TITLE,
        )
        self._title_label.place(relx=0.5, rely=0.5, anchor="center")
        self._header_frame = header

    def _setup_main_page(self, controls_frame_parent):
        """Construit le contenu de la page principale : photo produit + grille 2 colonnes."""
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

        self._toggle_rows["direct_mode"] = self._build_toggle_row(
            left, "direct", "Direct Mode", "Sans traitement du signal",
            self._direct_mode_var, self._on_direct_mode_change,
        )
        self._toggle_rows["scout_mode"] = self._build_toggle_row(
            left, "scout", "Scout Mode", "Détection des sons dans le jeu",
            self._scout_mode_var, self._on_scout_mode_change,
        )
        self._toggle_rows["crystalvoice"] = self._build_toggle_row(
            left, "voice", "CrystalVoice", "Optimisation de la voix en jeu",
            self._crystalvoice_var, self._on_crystalvoice_change,
        )

        self._direct_toggle_switch = self._toggle_rows["direct_mode"]["switch"]
        self._scout_toggle_switch = self._toggle_rows["scout_mode"]["switch"]
        self._crystalvoice_toggle_switch = self._toggle_rows["crystalvoice"]["switch"]

        self._build_sound_mode_row(right)
        self._build_equalizer_row(right)

    def _build_photo_header(self, parent):
        """Affiche la photo produit (coins arrondis) en tête de la page principale."""
        photo_path = ASSETS_DIR / "g8_photo.png"
        if not photo_path.exists():
            return
        # Référence conservée sur self : sinon le PhotoImage est ramassé par le GC.
        self._g8_photo_image = tk.PhotoImage(file=str(photo_path))
        tk.Label(
            parent, image=self._g8_photo_image, bg=theme.BG_WINDOW, bd=0, highlightthickness=0,
        ).pack(pady=(0, 24))

    def _build_row_icon_text(self, parent, icon: str, title: str, subtitle: str, subtitle_wrap: int = 280):
        """Construit une ligne badge d'icône + titre/sous-titre. Retourne (row, badge, title, subtitle)."""
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
        title: str,
        subtitle: str,
        variable: tk.BooleanVar,
        on_change: Callable[[], None],
    ) -> dict:
        """Construit une ligne badge + label/sous-titre + interrupteur à bascule."""
        row, badge, title_label, subtitle_label = self._build_row_icon_text(parent, icon, title, subtitle)
        switch = widgets.ToggleSwitch(row, variable=variable, command=on_change, bg=theme.BG_WINDOW)
        switch.pack(side=tk.RIGHT, anchor="n", padx=(16, 0))
        return {"badge": badge, "title": title_label, "subtitle": subtitle_label, "switch": switch}

    def _build_sound_mode_row(self, parent):
        """Bloc « Mode Sonore » : badge + label, sélecteur « split button » à droite."""
        row, _badge, _title, subtitle_label = self._build_row_icon_text(
            parent, "equalizer", "Mode Sonore", "Égaliseur et acoustic engine", subtitle_wrap=200,
        )
        self._sound_mode_label = subtitle_label
        self._sound_mode_select = widgets.SplitSelect(
            row, values=[], command=self._on_sound_mode_change, bg=theme.BG_WINDOW, width=230,
        )
        self._sound_mode_select.pack(side=tk.RIGHT, anchor="n", padx=(16, 0))

    def _build_equalizer_row(self, parent):
        """Ligne cliquable « Équaliseur » (badge + titre + mode actif), sans fond de carte."""
        row, badge, title_label, subtitle_label = self._build_row_icon_text(
            parent, "equalizer", "Équaliseur", "", subtitle_wrap=280,
        )
        self._eq_row = row
        self._eq_nav_badge = badge
        self._eq_nav_title = title_label
        self._eq_nav_subtitle = subtitle_label
        self._bind_click_recursive(row, self._on_eq_row_click)
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

    def _init_controller(self):
        """Initialise le contrôleur et se connecte au matériel."""
        from ..controller import get_controller
        self._controller = get_controller()
        self._switches = {
            "direct_mode": self._direct_toggle_switch,
            "scout_mode": self._scout_toggle_switch,
            "crystalvoice": self._crystalvoice_toggle_switch,
        }
        self._controller.add_listener("reconnecting", self._on_reconnecting)

        modes = self._controller.list_sound_modes()
        self._sound_mode_slugs = [slug for slug, _label in modes]
        self._sound_mode_labels = [label for _slug, label in modes]
        self._sound_mode_select.set_values(self._sound_mode_labels)
        self._select_sound_mode(self._controller.get_sound_mode())
        self._update_eq_button_label()

        self._eq_panel = EQPanel(
            self._eq_page, self._controller,
            status_callback=lambda text: self._status_label.config(text=text),
        )
        self._eq_panel.pack(fill=tk.BOTH, expand=True)

        if self._controller.connect():
            info = self._controller.get_debug_info()
            self._status_label.config(
                text=f"Connecté à Sound Blaster G8 (interface {info.get('interface_number')})"
            )
            self._load_current_state()
        else:
            self._status_label.config(
                text="Aucun matériel détecté - les commandes n'auront aucun effet"
            )

        self._apply_feature_availability()

    def _apply_feature_availability(self):
        """Grise les contrôles dont la trame USB n'a pas encore été reversée."""
        if not self._controller:
            return

        for feature in ("direct_mode", "scout_mode", "crystalvoice"):
            if not self._controller.is_feature_supported(feature):
                self._unavailable.add(feature)
                row = self._toggle_rows[feature]
                row["switch"].set_enabled(False)
                row["badge"].set_enabled(False)
                row["title"].config(fg=theme.FG_SECONDARY)
                row["subtitle"].config(
                    text=f"{row['subtitle'].cget('text')}\n(non implémenté)",
                    fg=theme.FG_SECONDARY,
                )

        if not self._controller.is_feature_supported("sound_mode"):
            self._unavailable.add("sound_mode")
            self._sound_mode_select.set_enabled(False)
            self._sound_mode_label.config(
                text=f"{self._sound_mode_label.cget('text')}\n(non implémenté)"
            )

        if not self._controller.is_feature_supported("eq"):
            self._unavailable.add("eq")
            self._set_eq_nav_enabled(False)

    def _load_current_state(self):
        """Charge l'état actuel depuis le contrôleur."""
        if not self._controller:
            return

        # Charger les états
        self._direct_mode_var.set(self._controller.get_direct_mode())
        self._scout_mode_var.set(self._controller.get_scout_mode())
        self._crystalvoice_var.set(self._controller.get_crystalvoice())
        self._select_sound_mode(self._controller.get_sound_mode())
        self._update_eq_button_label()

    def _select_sound_mode(self, slug: str) -> None:
        """Positionne le SplitSelect sur le mode sonore donné (sans déclencher l'event)."""
        if slug in self._sound_mode_slugs:
            self._sound_mode_select.set_index(self._sound_mode_slugs.index(slug))

    def _update_eq_button_label(self) -> None:
        """Rafraîchit le sous-texte de la ligne Équaliseur avec le mode actif."""
        if not self._controller:
            return
        slug = self._controller.get_sound_mode()
        label = slug
        for mode_slug, mode_label in self._controller.list_sound_modes():
            if mode_slug == slug:
                label = mode_label
                break
        self._eq_nav_subtitle.config(text=label)

    # ------------------------------------------------------------------
    # Navigation entre pages (pas de fenêtre flottante)
    # ------------------------------------------------------------------

    def _show_main_page(self):
        """Affiche la page principale (masque le bouton retour)."""
        self._eq_page.pack_forget()
        self._back_button.place_forget()
        self._title_label.config(text="Sound Blaster G8", font=theme.FONT_TITLE)
        self._main_page.pack(expand=True, fill=tk.BOTH)
        self._fit_window_to_page()

    def _show_eq_page(self):
        """Affiche la page Égaliseur (avec bouton retour en haut à gauche)."""
        self._main_page.pack_forget()
        self._back_button.place(x=24, rely=0.5, anchor="w")
        self._title_label.config(text="Équaliseur", font=theme.FONT_TITLE_EQ)
        self._eq_page.pack(expand=True, fill=tk.BOTH)
        self._fit_window_to_page()
        self._prepare_eq_page_async()

    def _prepare_eq_page_async(self):
        """Prépare l'égaliseur (active + applique un état plat si besoin).

        Comportement de l'app Creative native : si aucun égaliseur n'est
        déjà actif (mode « Désactivé »), applique un égaliseur plat (10
        bandes + Préampli à 0 dB) et l'active - sans quoi les écritures de
        bandes seraient bien acquittées par la carte mais resteraient
        inaudibles. Si un mode est déjà actif, ne fait rien. Ne bloque pas
        l'affichage : les sliders restent utilisables immédiatement.
        """
        if not self._controller:
            return

        def worker():
            try:
                ok = bool(self._controller.prepare_eq_page())
            except Exception as exc:  # pragma: no cover - dépend du matériel
                self.after(0, lambda: self._status_label.config(
                    text=f"Activation de l'égaliseur : erreur ({exc})"
                ))
                return
            if ok:
                def on_success():
                    self._status_label.config(text="Égaliseur activé")
                    if self._eq_panel is not None:
                        self._eq_panel.refresh()
                self.after(0, on_success)

        threading.Thread(target=worker, name="g8-eq-enable", daemon=True).start()

    def _fit_window_to_page(self):
        """Redimensionne la fenêtre pour que la page affichée tienne entière."""
        self.update_idletasks()
        width = max(MIN_WINDOW_WIDTH, self.winfo_reqwidth())
        height = self.winfo_reqheight()
        self.geometry(f"{width}x{height}")

    # ------------------------------------------------------------------
    # Bascules (exécutées hors du thread graphique)
    # ------------------------------------------------------------------

    def _on_reconnecting(self, active: bool) -> None:
        """Relais de l'événement ``reconnecting`` du contrôleur (worker thread)."""
        text = (
            "Direct Mode : reconnexion de la carte…"
            if active
            else "Carte reconnectée"
        )
        self.after(0, lambda: self._status_label.config(text=text))

    def _handle_toggle(
        self,
        name: str,
        label: str,
        var: tk.BooleanVar,
        setter: Callable[[bool], bool],
        getter: Optional[Callable[[], bool]] = None,
    ):
        """Applique un toggle dans un thread, puis resynchronise l'affichage.

        Le setter peut bloquer plusieurs secondes (reset USB du Direct Mode) :
        l'interrupteur est désactivé pendant l'opération et le résultat est
        appliqué dans le thread Tk.
        """
        if not self._controller:
            return

        requested = var.get()
        switch = self._switches.get(name)
        if switch is not None:
            switch.set_enabled(False)
        self._status_label.config(text=f"{label} : envoi de la commande…")

        def worker():
            error: Optional[Exception] = None
            ok = False
            state: Optional[bool] = None
            try:
                ok = bool(setter(requested))
                if getter is not None:
                    # Relire l'état matériel réel : après un reset USB, la
                    # carte est seule source de vérité.
                    state = getter()
            except Exception as exc:  # pragma: no cover - dépend du matériel
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
        """Fin d'une bascule : réactive l'interrupteur et affiche l'état réel."""
        switch = self._switches.get(name)
        if switch is not None and name not in self._unavailable:
            switch.set_enabled(True)

        # État affiché : celui du matériel s'il a pu être relu, sinon celui
        # demandé (succès) ou l'ancien (échec).
        effective = state if state is not None else (requested if ok else not requested)
        var.set(effective)

        if error is not None:
            self._status_label.config(text=f"{label} : erreur ({error})")
        elif ok:
            self._status_label.config(
                text=f"{label} {'activé' if effective else 'désactivé'}"
            )
        else:
            self._status_label.config(
                text=f"{label} : échec de la commande (voir la console)"
            )

    def _on_direct_mode_change(self):
        """Gère le changement du Direct Mode."""
        self._handle_toggle(
            "direct_mode", "Direct Mode", self._direct_mode_var,
            lambda v: self._controller.set_direct_mode(v),
            getter=lambda: self._controller.get_direct_mode(),
        )

    def _on_scout_mode_change(self):
        """Gère le changement du Scout Mode."""
        self._handle_toggle(
            "scout_mode", "Scout Mode", self._scout_mode_var,
            lambda v: self._controller.set_scout_mode(v),
            getter=lambda: self._controller.get_scout_mode(),
        )

    def _on_crystalvoice_change(self):
        """Gère le changement du CrystalVoice."""
        self._handle_toggle(
            "crystalvoice", "CrystalVoice", self._crystalvoice_var,
            lambda v: self._controller.set_crystalvoice(v),
        )

    def _on_sound_mode_change(self, index: int):
        """Gère la sélection d'un mode sonore dans le SplitSelect."""
        if not self._controller:
            return

        if index < 0 or index >= len(self._sound_mode_slugs):
            return
        slug = self._sound_mode_slugs[index]
        label = self._sound_mode_labels[index]

        self._sound_mode_select.set_enabled(False)
        self._status_label.config(text=f"Mode Sonore « {label} » : envoi de la commande…")

        def worker():
            error: Optional[Exception] = None
            ok = False
            try:
                ok = bool(self._controller.set_sound_mode(slug))
            except Exception as exc:  # pragma: no cover - dépend du matériel
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
        """Fin de la sélection d'un mode sonore : réactive le SplitSelect."""
        if "sound_mode" not in self._unavailable:
            self._sound_mode_select.set_enabled(True)

        # En cas d'échec, resynchroniser l'affichage sur l'état réel du contrôleur.
        self._select_sound_mode(self._controller.get_sound_mode())
        self._update_eq_button_label()
        if self._eq_panel is not None:
            self._eq_panel.refresh()

        if error is not None:
            self._status_label.config(text=f"Mode Sonore : erreur ({error})")
        elif ok:
            self._status_label.config(text=f"Mode Sonore « {label} » appliqué")
        else:
            self._status_label.config(
                text=f"Mode Sonore « {label} » : échec de la commande (voir la console)"
            )
