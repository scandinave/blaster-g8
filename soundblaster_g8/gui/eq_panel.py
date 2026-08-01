"""
Page Égaliseur (10 bandes + Préampli/Basse/Aigus) pour la Sound Blaster G8.

Page intégrée à ``MainWindow`` (pas de fenêtre flottante) : voir
``main_window.py`` pour la navigation (``_show_eq_page``/``_show_main_page``).
Chaque bande et le Préampli se pilotent avec le même mécanisme validé sur le
matériel que le Mode Sonore (``CMD_SET_FLOAT``, voir ``driver.eq_set_band``/
``driver.eq_set_preamp``). Basse et Aigus n'ont pas de paramètre dédié sur la
carte : voir ``controller.set_eq_bass``/``set_eq_treble`` pour l'approximation
utilisée (dérivée de la capture ``Equalizer-manual.pcapng``) - ces deux
sliders restent à la position posée par l'utilisateur (comme l'app Creative
native), le contrôleur ne mémorisant qu'un delta interne.
"""

import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from ..controller import SoundBlasterController


class EQPanel(ttk.Frame):
    """Page intégrée pour l'égaliseur 10 bandes + Préampli/Basse/Aigus."""

    FREQUENCY_BANDS = [
        "32 Hz", "64 Hz", "125 Hz", "250 Hz", "500 Hz",
        "1 kHz", "2 kHz", "4 kHz", "8 kHz", "16 kHz"
    ]

    def __init__(
        self,
        parent,
        controller: SoundBlasterController,
        status_callback: Optional[Callable[[str], None]] = None,
    ):
        """Initialise la page EQ.

        Args:
            parent: conteneur parent (la page EQ de MainWindow)
            controller: instance du contrôleur SoundBlaster
            status_callback: callback optionnel pour afficher le statut d'une
                écriture de bande/slider dans la barre de statut partagée
        """
        super().__init__(parent)

        self.controller = controller
        self._status_callback = status_callback
        self._band_vars: list[tk.DoubleVar] = []
        self._preamp_var = tk.DoubleVar(value=controller.get_eq_preamp())
        # Basse/Aigus n'ont pas de paramètre dédié sur la carte, mais leur
        # position reste affichée telle que posée par l'utilisateur (voir
        # controller.set_eq_bass/set_eq_treble).
        self._bass_var = tk.DoubleVar(value=controller.get_eq_bass())
        self._treble_var = tk.DoubleVar(value=controller.get_eq_treble())

        # Charger les bandes actuelles
        eq_bands = controller.get_eq_all_bands()
        for value in eq_bands:
            var = tk.DoubleVar(value=value)
            self._band_vars.append(var)

        self._setup_ui()

    def _setup_ui(self):
        """Configure l'interface de l'égaliseur."""
        self._sliders: list[ttk.Scale] = []
        self._labels: list[tk.Label] = []

          # Préampli - même mécanique qu'une bande (paramètre dédié, exact)
        preamp_frame = ttk.LabelFrame(self, text="Préampli", padding=10)
        preamp_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        self._preamp_slider, self._preamp_label = self._add_slider_row(
            preamp_frame, "Gain", self._preamp_var, self._commit_preamp,
        )

          # Basse / Aigus - approximation (voir docstring du module)
        tilt_frame = ttk.LabelFrame(
            self, text="Tonalité (approximatif)", padding=10,
        )
        tilt_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        self._bass_slider, self._bass_label = self._add_slider_row(
            tilt_frame, "Basse", self._bass_var,
            lambda: self._commit_tilt("Basse", self._bass_var, self.controller.set_eq_bass),
        )
        self._treble_slider, self._treble_label = self._add_slider_row(
            tilt_frame, "Aigus", self._treble_var,
            lambda: self._commit_tilt("Aigus", self._treble_var, self.controller.set_eq_treble),
        )

          # Cadre des sliders EQ (10 bandes)
        eq_container = ttk.LabelFrame(self, text="Bandes", padding=10)
        eq_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 5))

        for i in range(len(self._band_vars)):
            scale, label = self._add_slider_row(
                eq_container, self.FREQUENCY_BANDS[i], self._band_vars[i],
                lambda idx=i: self._commit_band(idx),
            )
            self._sliders.append(scale)
            self._labels.append(label)

          # Cadre des presets
        preset_frame = ttk.LabelFrame(self, text="Presets Rapides", padding=10)
        preset_frame.pack(fill=tk.X, padx=10, pady=5)

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

          # Commande de réinitialisation
        cmd_frame = ttk.Frame(self, padding=(10, 5, 10, 10))
        cmd_frame.pack(fill=tk.X)

        reset_btn = ttk.Button(
            cmd_frame,
            text="Réinitialiser tout",
            command=self._reset_all
        )
        reset_btn.pack(side=tk.RIGHT)

    def _add_slider_row(
        self,
        parent,
        label_text: str,
        var: tk.DoubleVar,
        on_release: Callable[[], None],
    ) -> tuple[ttk.Scale, tk.Label]:
        """Construit une ligne slider horizontal + label fréquence/valeur.

        Le ``command=`` du slider ne fait que suivre le glissement
        (affichage local) ; l'envoi matériel se fait au relâchement
        (``<ButtonRelease-1>``) pour ne pas saturer le canal de contrôle HID.
        """
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)

        name_label = ttk.Label(row, text=label_text, width=10)
        name_label.pack(side=tk.LEFT, padx=(0, 5))

        value_label = tk.Label(row, text=f"{var.get():+.1f} dB", width=6)

        def on_drag(val, _var=var, _label=value_label):
            _var.set(float(val))
            _label.config(text=f"{_var.get():+.1f} dB")

        scale = ttk.Scale(
            row, from_=-12, to=12, orient=tk.HORIZONTAL, variable=var,
            command=on_drag,
        )
        scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        scale.bind("<ButtonRelease-1>", lambda _event: on_release())

        value_label.pack(side=tk.RIGHT)
        return scale, value_label

    def refresh(self) -> None:
        """Resynchronise tous les sliders sur l'état connu du contrôleur.

        Appelé par ``MainWindow`` après une sélection de mode sonore ou une
        activation « plate » de l'égaliseur (``prepare_eq_page``), qui
        remplacent les bandes/Préampli et réinitialisent Basse/Aigus à 0
        sans passer par cette page.
        """
        eq_bands = self.controller.get_eq_all_bands()
        for i, var in enumerate(self._band_vars):
            if i < len(eq_bands):
                var.set(eq_bands[i])
                self._labels[i].config(text=f"{eq_bands[i]:+.1f} dB")
        preamp = self.controller.get_eq_preamp()
        self._preamp_var.set(preamp)
        self._preamp_label.config(text=f"{preamp:+.1f} dB")
        bass = self.controller.get_eq_bass()
        self._bass_var.set(bass)
        self._bass_label.config(text=f"{bass:+.1f} dB")
        treble = self.controller.get_eq_treble()
        self._treble_var.set(treble)
        self._treble_label.config(text=f"{treble:+.1f} dB")

    def _commit_band(self, index: int):
        """Envoie la valeur d'une bande à la carte (au relâchement du curseur)."""
        if not (0 <= index < len(self._band_vars)):
            return
        value = self._band_vars[index].get()
        label = self.FREQUENCY_BANDS[index]
        self._run_commit(
            f"Bande {label}", value,
            lambda: self.controller.set_eq_band(index, value),
        )

    def _commit_preamp(self):
        """Envoie la valeur du Préampli à la carte (au relâchement du curseur)."""
        value = self._preamp_var.get()
        self._run_commit(
            "Préampli", value,
            lambda: self.controller.set_eq_preamp(value),
        )

    def _commit_tilt(self, label: str, var: tk.DoubleVar, setter: Callable[[float], bool]):
        """Envoie une nouvelle position Basse/Aigus (approximatif).

        Le slider reste où l'utilisateur l'a posé (voir
        ``controller.set_eq_bass``/``set_eq_treble``) : seules les 10 bandes
        affichées sont resynchronisées après coup, l'approximation les
        modifiant toutes.
        """
        value = var.get()
        self._set_status(f"{label} : envoi de {value:+.1f} dB (approximatif)…")

        def worker():
            error: Optional[Exception] = None
            ok = False
            try:
                ok = bool(setter(value))
            except Exception as exc:  # pragma: no cover - dépend du matériel
                error = exc
            self.after(0, lambda: self._finish_tilt(label, value, ok, error))

        threading.Thread(target=worker, name=f"g8-eq-tilt-{label}", daemon=True).start()

    def _finish_tilt(self, label: str, value: float, ok: bool, error: Optional[Exception]):
        self.refresh()
        if error is not None:
            self._set_status(f"{label} : erreur ({error})")
        elif ok:
            self._set_status(f"{label} : {value:+.1f} dB appliqué (approximatif)")
        else:
            self._set_status(f"{label} : échec de la commande (voir la console)")

    def _run_commit(self, label: str, value: float, action: Callable[[], bool]):
        """Exécute une écriture matérielle unique dans un thread de travail."""
        self._set_status(f"{label} : envoi de {value:+.1f} dB…")

        def worker():
            error: Optional[Exception] = None
            ok = False
            try:
                ok = bool(action())
            except Exception as exc:  # pragma: no cover - dépend du matériel
                error = exc
            self.after(0, lambda: self._finish_commit(label, value, ok, error))

        threading.Thread(target=worker, name=f"g8-eq-{label}", daemon=True).start()

    def _finish_commit(self, label: str, value: float, ok: bool, error: Optional[Exception]):
        if error is not None:
            self._set_status(f"{label} : erreur ({error})")
        elif ok:
            self._set_status(f"{label} : {value:+.1f} dB appliquée")
        else:
            self._set_status(f"{label} : échec de la commande (voir la console)")

    def _set_status(self, text: str) -> None:
        if self._status_callback is not None:
            self._status_callback(text)

    def _apply_preset(self, preset_name: str):
        """Applique un preset à toutes les bandes."""
        self.controller.load_preset(preset_name)
        self.refresh()
        self._set_status(f"Preset « {preset_name.replace('_', ' ').title()} » appliqué")

    def _reset_all(self):
        """Réinitialise toutes les bandes à 0 dB."""
        self._apply_preset("flat")
