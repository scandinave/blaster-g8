"""
EQ Panel pour l'égaliseur à 10 bandes de Sound Blaster G8.
Interface dédiée avec sliders verticaux.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional

from ..controller import SoundBlasterController


class EQPanel(tk.Toplevel):
    """Fenêtre secondaire pour l'égaliseur 10 bandes."""

    FREQUENCY_BANDS = [
        "32 Hz", "64 Hz", "125 Hz", "250 Hz", "500 Hz",
        "1 kHz", "2 kHz", "4 kHz", "8 kHz", "16 kHz"
    ]

    def __init__(self, parent, controller: SoundBlasterController):
        """Initialise la fenêtre EQ.

        Args:
            parent: Fenêtre parente (MainWindow)
            controller: Instance du contrôleur SoundBlaster
        """
        super().__init__(parent)

        self.controller = controller
        self._band_vars: list[tk.DoubleVar] = []

         # Configuration de la fenêtre
        self.title("Égaliseur - Sound Blaster G8")
        self.geometry("400x520")
        self.resizable(False, False)
        self.transient(parent)
        self.gravity = "center"

         # Charger les bandes actuelles
        eq_bands = controller.get_eq_all_bands()
        for value in eq_bands:
            var = tk.DoubleVar(value=value)
            self._band_vars.append(var)

         # Configuration de l'interface
        self._setup_ui()

    def _setup_ui(self):
        """Configure l'interface de l'égaliseur."""
          # En-tête avec titre
        header_frame = ttk.Frame(self, padding=(10, 10, 10, 5))
        header_frame.pack(fill=tk.X)

        title_label = tk.Label(
            header_frame,
            text="Égaliseur 10 Bandes",
            font=("Helvetica", 14, "bold")
        )
        title_label.pack()

          # Cadre des sliders EQ
        eq_container = ttk.Frame(self, padding=10)
        eq_container.pack(fill=tk.BOTH, expand=True)

          # Créer les sliders verticaux pour chaque bande
        self._sliders: list[ttk.Scale] = []
        self._labels: list[tk.Label] = []

        for i in range(len(self._band_vars)):
             # Frame pour la bande
            band_frame = ttk.Frame(eq_container)
            band_frame.pack(fill=tk.X, pady=2)

             # Label fréquence (gauche)
            freq_label = ttk.Label(
                band_frame,
                text=self.FREQUENCY_BANDS[i],
                width=10
            )
            freq_label.pack(side=tk.LEFT, padx=(0, 5))

             # Slider vertical
            scale = ttk.Scale(
                band_frame,
                from_=-12,
                to=12,
                orient=tk.HORIZONTAL,
                variable=self._band_vars[i],
                command=lambda val, idx=i: self._on_band_change(idx, float(val))
            )
            scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

             # Label valeur (droite)
            value_label = ttk.Label(
                band_frame,
                text=f"{self._band_vars[i].get():+.1f} dB",
                width=6
            )
            value_label.pack(side=tk.RIGHT)

            self._sliders.append(scale)
            self._labels.append(value_label)

          # Cadre des presets
        preset_frame = ttk.LabelFrame(self, text="Presets Rapides", padding=10)
        preset_frame.pack(fill=tk.X, pady=(10, 5))

        preset_grid = ttk.Frame(preset_frame)
        preset_grid.pack(fill=tk.X)

        presets = ["flat", "bass_boost", "vocal", "gaming", "movie"]
        for i, preset in enumerate(presets):
            btn = ttk.Button(
                preset_grid,
                text=preset.replace("_", " ").title(),
                command=lambda p=preset: self._apply_preset(p)
            )
            btn.grid(row=i // 2, column=i % 2, padx=5, pady=5, sticky="ew")

          # Commandes principales
        cmd_frame = ttk.Frame(self, padding=(10, 5, 10, 10))
        cmd_frame.pack(fill=tk.X)

        save_btn = ttk.Button(
            cmd_frame,
            text="Sauvegarder le preset actuel...",
            command=self._save_preset
        )
        save_btn.pack(side=tk.LEFT, padx=(0, 5))

        reset_btn = ttk.Button(
            cmd_frame,
            text="Réinitialiser tout",
            command=self._reset_all
        )
        reset_btn.pack(side=tk.RIGHT)

          # Frame pour sauvegarder preset personnalisé
        self._save_custom_frame = ttk.Frame(self)
        self._save_custom_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        self._save_custom_frame.pack_forget()   # Caché par défaut

          # Mise à jour dynamique des labels de valeur
        for i, var in enumerate(self._band_vars):
            var.trace_add("write", lambda *args, idx=i: self._update_label(idx))

    def _on_band_change(self, index: int, value: float):
        """Gère le changement d'une bande."""
        if 0 <= index < len(self._band_vars):
            self._band_vars[index].set(value)
            self.controller.set_eq_band(index, value)

    def _update_label(self, index: int):
        """Met à jour l'affichage de la valeur pour une bande spécifique."""
        if 0 <= index < len(self._labels):
            value = self._band_vars[index].get()
            self._labels[index].config(text=f"{value:+.1f} dB")

    def _apply_preset(self, preset_name: str):
        """Applique un preset à toutes les bandes."""
        try:
            self.controller.load_preset(preset_name)
             # Mettre à jour les variables locales
            eq_bands = self.controller.get_eq_all_bands()
            for i, var in enumerate(self._band_vars):
                var.set(eq_bands[i])
                 # Mettre à jour les labels
            for i in range(len(self._labels)):
                self._update_label(i)
        except ValueError as e:
            messagebox.showerror("Erreur", str(e))

    def _save_preset(self):
        """Ouvre une fenêtre pour sauvegarder un preset personnalisé."""
        save_window = tk.Toplevel(self)
        save_window.title("Sauvegarder le preset")
        save_window.geometry("250x100")
        save_window.transient(self)
        save_window.gravity = "center"

        ttk.Label(save_window, text="Nom du preset:").pack(pady=(10, 5))

        name_entry = ttk.Entry(save_window, width=30)
        name_entry.pack(pady=5)

        def confirm_save():
            name = name_entry.get().strip()
            if name:
                self.controller.save_preset(name)
                save_window.destroy()
                messagebox.showinfo("Succès", f"Preset '{name}' sauvegardé !")
            else:
                messagebox.showwarning("Attention", "Veuillez entrer un nom.")

        ttk.Button(save_window, text="Sauvegarder", command=confirm_save).pack(pady=5)

    def _reset_all(self):
        """Réinitialise toutes les bandes à 0 dB."""
        self.controller.load_preset("flat")
        for var in self._band_vars:
            var.set(0.0)
        for label in self._labels:
            label.config(text="+0.0 dB")