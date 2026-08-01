"""
MainWindow pour l'application de contrôle Sound Blaster G8.
Interface Tkinter avec les contrôles principaux.

Les commandes matérielles sont exécutées dans un thread de travail : une
bascule du Direct Mode provoque un reset USB de la carte et prend 2 à 4
secondes, ce qui gèlerait la fenêtre si elle était faite dans le callback Tk.
Le résultat est rapatrié dans le thread graphique via ``self.after(0, ...)``.
"""

import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from ..controller import SoundBlasterController


class MainWindow(tk.Tk):
    """Fenêtre principale de l'application Sound Blaster G8."""

    def __init__(self):
        """Initialise la fenêtre principale."""
        super().__init__()

        self.title("Sound Blaster G8 - Control")
        self.geometry("600x450")
        self.resizable(True, True)

        # Controller singleton
        self._controller: Optional[SoundBlasterController] = None

        # État des toggles
        self._direct_mode_var = tk.BooleanVar(value=False)
        self._scout_mode_var = tk.BooleanVar(value=False)
        self._crystalvoice_var = tk.BooleanVar(value=False)

        # Mode sonore : liste (slug, label) et variable liée au Combobox.
        self._sound_mode_slugs: list[str] = []
        self._sound_mode_var = tk.StringVar(value="")

        # Interrupteurs indisponibles (fonction non reversée) : ils ne doivent
        # pas être réactivés à la fin d'une commande.
        self._unavailable: set[str] = set()
        self._switches: dict[str, tk.Checkbutton] = {}

        # Configuration de la fenêtre
        self._setup_ui()

    def _setup_ui(self):
        """Configure l'interface utilisateur."""
        # Titre
        title_frame = tk.Frame(self, pady=10)
        title_frame.pack(fill=tk.X)

        title_label = tk.Label(
            title_frame,
            text="Sound Blaster G8",
            font=("Helvetica", 16, "bold")
        )
        title_label.pack()

         # Cadre des contrôles principaux
        controls_frame = ttk.Frame(self, padding=20)
        controls_frame.pack(expand=True, fill=tk.BOTH)

          # Direct Mode - Cadre personnalisé pour le bouton avec texte sur deux lignes
        direct_frame = ttk.Frame(controls_frame, padding=10)
        direct_frame.pack(fill=tk.X, pady=(0, 10))

        self._direct_toggle_frame = tk.Frame(direct_frame)
        self._direct_toggle_frame.pack(expand=True, fill=tk.X, padx=10, pady=5)

        self._direct_toggle_label = ttk.Label(
            self._direct_toggle_frame,
            text="Direct Mode\nSans traitement du signal",
            justify=tk.LEFT
           )
        self._direct_toggle_label.pack(side=tk.LEFT, expand=True, fill=tk.X)

        self._direct_toggle_switch = tk.Checkbutton(
            self._direct_toggle_frame,
            variable=self._direct_mode_var,
            command=self._on_direct_mode_change
           )
        self._direct_toggle_switch.pack(side=tk.RIGHT)

          # Scout Mode - Cadre personnalisé pour le bouton avec texte sur deux lignes
        scout_frame = ttk.Frame(controls_frame, padding=10)
        scout_frame.pack(fill=tk.X, pady=(0, 10))

        self._scout_toggle_frame = tk.Frame(scout_frame)
        self._scout_toggle_frame.pack(expand=True, fill=tk.X, padx=10, pady=5)

        self._scout_toggle_label = ttk.Label(
            self._scout_toggle_frame,
            text="Scout Mode\nDétection des sons dans le jeu",
            justify=tk.LEFT
           )
        self._scout_toggle_label.pack(side=tk.LEFT, expand=True, fill=tk.X)

        self._scout_toggle_switch = tk.Checkbutton(
            self._scout_toggle_frame,
            variable=self._scout_mode_var,
            command=self._on_scout_mode_change
           )
        self._scout_toggle_switch.pack(side=tk.RIGHT)

          # CrystalVoice - Cadre personnalisé pour le bouton avec texte sur deux lignes
        crystalvoice_frame = ttk.Frame(controls_frame, padding=10)
        crystalvoice_frame.pack(fill=tk.X, pady=(0, 10))

        self._crystalvoice_toggle_frame = tk.Frame(crystalvoice_frame)
        self._crystalvoice_toggle_frame.pack(expand=True, fill=tk.X, padx=10, pady=5)

        self._crystalvoice_toggle_label = ttk.Label(
            self._crystalvoice_toggle_frame,
            text="CrystalVoice\nOptimisation de la voix en jeu",
            justify=tk.LEFT
           )
        self._crystalvoice_toggle_label.pack(side=tk.LEFT, expand=True, fill=tk.X)

        self._crystalvoice_toggle_switch = tk.Checkbutton(
            self._crystalvoice_toggle_frame,
            variable=self._crystalvoice_var,
            command=self._on_crystalvoice_change
           )
        self._crystalvoice_toggle_switch.pack(side=tk.RIGHT)

          # Mode Sonore - sélection parmi les modes reversés depuis les captures
        sound_mode_frame = ttk.Frame(controls_frame, padding=10)
        sound_mode_frame.pack(fill=tk.X, pady=(0, 10))

        self._sound_mode_inner_frame = tk.Frame(sound_mode_frame)
        self._sound_mode_inner_frame.pack(expand=True, fill=tk.X, padx=10, pady=5)

        self._sound_mode_label = ttk.Label(
            self._sound_mode_inner_frame,
            text="Mode Sonore\nÉgaliseur et acoustic engine",
            justify=tk.LEFT
           )
        self._sound_mode_label.pack(side=tk.LEFT, expand=True, fill=tk.X)

        self._sound_mode_combo = ttk.Combobox(
            self._sound_mode_inner_frame,
            textvariable=self._sound_mode_var,
            state="readonly",
            width=28,
           )
        self._sound_mode_combo.pack(side=tk.RIGHT)
        self._sound_mode_combo.bind("<<ComboboxSelected>>", self._on_sound_mode_change)

        # Section EQ
        eq_frame = ttk.LabelFrame(controls_frame, text="Égaliseur", padding=10)
        eq_frame.pack(fill=tk.X, pady=(0, 10))

        self._eq_button = ttk.Button(
            eq_frame,
            text="Configurer\nAccès à l'égaliseur 10 bandes",
            command=self._open_eq_panel
         )
        self._eq_button.pack(side=tk.LEFT, expand=True, fill=tk.X)

        # Status bar
        status_bar = tk.Frame(self, relief=tk.SUNKEN, bd=1)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self._status_label = tk.Label(
            status_bar,
            text="Prêt",
            anchor=tk.W
        )
        self._status_label.pack(expand=True, fill=tk.X, padx=5, pady=2)

        # Initialisation du controller
        self._init_controller()

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
        self._sound_mode_combo.config(values=[label for _slug, label in modes])
        self._select_sound_mode(self._controller.get_sound_mode())

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

        for feature, switch, label in (
            ("direct_mode", self._direct_toggle_switch, self._direct_toggle_label),
            ("scout_mode", self._scout_toggle_switch, self._scout_toggle_label),
            ("crystalvoice", self._crystalvoice_toggle_switch,
             self._crystalvoice_toggle_label),
        ):
            if not self._controller.is_feature_supported(feature):
                self._unavailable.add(feature)
                switch.config(state=tk.DISABLED)
                label.config(text=f"{label.cget('text')}\n(non implémenté)")

        if not self._controller.is_feature_supported("sound_mode"):
            self._unavailable.add("sound_mode")
            self._sound_mode_combo.config(state=tk.DISABLED)
            self._sound_mode_label.config(
                text=f"{self._sound_mode_label.cget('text')}\n(non implémenté)"
            )

        if not self._controller.is_feature_supported("eq"):
            self._eq_button.config(state=tk.DISABLED)

    def _load_current_state(self):
        """Charge l'état actuel depuis le contrôleur."""
        if not self._controller:
            return

        # Charger les états
        self._direct_mode_var.set(self._controller.get_direct_mode())
        self._scout_mode_var.set(self._controller.get_scout_mode())
        self._crystalvoice_var.set(self._controller.get_crystalvoice())
        self._select_sound_mode(self._controller.get_sound_mode())

    def _select_sound_mode(self, slug: str) -> None:
        """Positionne le Combobox sur le mode sonore donné (sans déclencher l'event)."""
        if slug in self._sound_mode_slugs:
            self._sound_mode_combo.current(self._sound_mode_slugs.index(slug))

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
            switch.config(state=tk.DISABLED)
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
            switch.config(state=tk.NORMAL)

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

    def _on_sound_mode_change(self, _event=None):
        """Gère la sélection d'un mode sonore dans le Combobox."""
        if not self._controller:
            return

        index = self._sound_mode_combo.current()
        if index < 0 or index >= len(self._sound_mode_slugs):
            return
        slug = self._sound_mode_slugs[index]
        label = self._sound_mode_combo.get()

        self._sound_mode_combo.config(state=tk.DISABLED)
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
        """Fin de la sélection d'un mode sonore : réactive le Combobox."""
        if "sound_mode" not in self._unavailable:
            self._sound_mode_combo.config(state="readonly")

        # En cas d'échec, resynchroniser l'affichage sur l'état réel du contrôleur.
        self._select_sound_mode(self._controller.get_sound_mode())

        if error is not None:
            self._status_label.config(text=f"Mode Sonore : erreur ({error})")
        elif ok:
            self._status_label.config(text=f"Mode Sonore « {label} » appliqué")
        else:
            self._status_label.config(
                text=f"Mode Sonore « {label} » : échec de la commande (voir la console)"
            )

    def _open_eq_panel(self):
        """Ouvre le panneau d'égaliseur."""
        from .eq_panel import EQPanel
        eq_window = EQPanel(self, self._controller)