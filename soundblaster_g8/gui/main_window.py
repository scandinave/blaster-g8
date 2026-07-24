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
        self.geometry("500x400")
        self.resizable(False, False)

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

        # Direct Mode
        direct_frame = ttk.LabelFrame(controls_frame, text="Direct Mode", padding=10)
        direct_frame.pack(fill=tk.X, pady=(0, 10))

        direct_label = ttk.Label(
            direct_frame,
            text="Mode direct: sans traitement du signal"
        )
        direct_label.pack(pady=(0, 5))

        self._direct_toggle = ttk.Checkbutton(
            direct_frame,
            variable=self._direct_mode_var,
            command=self._on_direct_mode_change
        )
        self._direct_toggle.pack()

        # Scout Mode
        scout_frame = ttk.LabelFrame(controls_frame, text="Scout Mode", padding=10)
        scout_frame.pack(fill=tk.X, pady=(0, 10))

        scout_label = ttk.Label(
            scout_frame,
            text="Mode Scout: détecte les sons dans le jeu"
        )
        scout_label.pack(pady=(0, 5))

        self._scout_toggle = ttk.Checkbutton(
            scout_frame,
            variable=self._scout_mode_var,
            command=self._on_scout_mode_change
        )
        self._scout_toggle.pack()

        # CrystalVoice
        crystalvoice_frame = ttk.LabelFrame(controls_frame, text="CrystalVoice", padding=10)
        crystalvoice_frame.pack(fill=tk.X, pady=(0, 10))

        crystalvoice_label = ttk.Label(
            crystalvoice_frame,
            text="CrystalVoice: optimisation de la voix en jeu"
        )
        crystalvoice_label.pack(pady=(0, 5))

        self._crystalvoice_toggle = ttk.Checkbutton(
            crystalvoice_frame,
            variable=self._crystalvoice_var,
            command=self._on_crystalvoice_change
        )
        self._crystalvoice_toggle.pack()

        # Section EQ
        eq_frame = ttk.LabelFrame(controls_frame, text="Égaliseur", padding=10)
        eq_frame.pack(fill=tk.X, pady=(0, 10))

        eq_info = ttk.Label(
            eq_frame,
            text="Cliquez sur 'Configurer' pour accéder à l'égaliseur 10 bandes"
        )
        eq_info.pack(pady=(0, 5))

        self._eq_button = ttk.Button(
            eq_frame,
            text="Configurer",
            command=self._open_eq_panel
        )
        self._eq_button.pack()

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
            self._status_label.config(text="Connecté à Sound Blaster G8")
            self._load_current_state()
        else:
            self._status_label.config(text="Mode simulation (pas de matériel détecté)")

    def _load_current_state(self):
        """Charge l'état actuel depuis le contrôleur."""
        if not self._controller:
            return

        # Charger les états
        self._direct_mode_var.set(self._controller.get_direct_mode())
        self._scout_mode_var.set(self._controller.get_scout_mode())
        self._crystalvoice_var.set(self._controller.get_crystalvoice())

    def _on_direct_mode_change(self):
        """Gère le changement du Direct Mode."""
        if self._controller:
            self._controller.set_direct_mode(self._direct_mode_var.get())
            state = "activé" if self._direct_mode_var.get() else "désactivé"
            self._status_label.config(text=f"Direct Mode {state}")

    def _on_scout_mode_change(self):
        """Gère le changement du Scout Mode."""
        if self._controller:
            self._controller.set_scout_mode(self._scout_mode_var.get())
            state = "activé" if self._scout_mode_var.get() else "désactivé"
            self._status_label.config(text=f"Scout Mode {state}")

    def _on_crystalvoice_change(self):
        """Gère le changement du CrystalVoice."""
        if self._controller:
            self._controller.set_crystalvoice(self._crystalvoice_var.get())
            state = "activé" if self._crystalvoice_var.get() else "désactivé"
            self._status_label.config(text=f"CrystalVoice {state}")

    def _open_eq_panel(self):
        """Ouvre le panneau d'égaliseur."""
        from .eq_panel import EQPanel
        eq_window = EQPanel(self, self._controller)