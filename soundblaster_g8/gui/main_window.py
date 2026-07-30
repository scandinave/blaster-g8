"""
MainWindow pour l'application de contrôle Sound Blaster G8.
Interface Tkinter avec les contrôles principaux.
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional

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
                switch.config(state=tk.DISABLED)
                label.config(text=f"{label.cget('text')}\n(non implémenté)")

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

    def _handle_toggle(self, name: str, label: str, var: tk.BooleanVar, setter):
        """Applique un toggle et annule l'affichage si la carte refuse."""
        if not self._controller:
            return

        requested = var.get()
        if setter(requested):
            state = "activé" if requested else "désactivé"
            self._status_label.config(text=f"{label} {state}")
        else:
            # La carte n'a pas confirmé : on remet l'interrupteur dans son
            # état précédent pour ne pas afficher un état mensonger.
            var.set(not requested)
            self._status_label.config(
                text=f"{label} : échec de la commande (voir la console)"
            )

    def _on_direct_mode_change(self):
        """Gère le changement du Direct Mode."""
        self._handle_toggle(
            "direct_mode", "Direct Mode", self._direct_mode_var,
            lambda v: self._controller.set_direct_mode(v),
        )

    def _on_scout_mode_change(self):
        """Gère le changement du Scout Mode."""
        self._handle_toggle(
            "scout_mode", "Scout Mode", self._scout_mode_var,
            lambda v: self._controller.set_scout_mode(v),
        )

    def _on_crystalvoice_change(self):
        """Gère le changement du CrystalVoice."""
        self._handle_toggle(
            "crystalvoice", "CrystalVoice", self._crystalvoice_var,
            lambda v: self._controller.set_crystalvoice(v),
        )

    def _open_eq_panel(self):
        """Ouvre le panneau d'égaliseur."""
        from .eq_panel import EQPanel
        eq_window = EQPanel(self, self._controller)