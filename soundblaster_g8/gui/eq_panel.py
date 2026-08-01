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

Cartes et sliders reprennent le style du mockup de design (fond sombre,
piste fine + curseur rond) : voir ``theme.py``/``widgets.py``.
"""

import threading
import tkinter as tk
from typing import Callable, Optional

from ..controller import SoundBlasterController
from . import theme, widgets

PRESET_LABELS = {
    "flat": "Flat",
    "bass_boost": "Bass Boost",
    "vocal": "Vocal",
    "gaming": "Gaming",
    "movie": "Movie",
}


class EQPanel(tk.Frame):
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
        super().__init__(parent, bg=theme.BG_WINDOW)

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
        self._sliders: list[widgets.Slider] = []
        self._labels: list[tk.Label] = []

        container = tk.Frame(self, bg=theme.BG_WINDOW)
        container.pack(fill=tk.BOTH, expand=True, padx=36, pady=(16, 0))

        # Préampli - même mécanique qu'une bande (paramètre dédié, exact)
        preamp_card = self._build_card(container, "Préampli")
        self._preamp_slider, self._preamp_label = self._add_slider_row(
            preamp_card, "Gain", self._preamp_var, self._commit_preamp,
        )

        # Basse / Aigus - approximation (voir docstring du module)
        tilt_card = self._build_card(container, "Tonalité (approximatif)")
        self._bass_slider, self._bass_label = self._add_slider_row(
            tilt_card, "Basse", self._bass_var,
            lambda: self._commit_tilt("Basse", self._bass_var, self.controller.set_eq_bass),
        )
        self._treble_slider, self._treble_label = self._add_slider_row(
            tilt_card, "Aigus", self._treble_var,
            lambda: self._commit_tilt("Aigus", self._treble_var, self.controller.set_eq_treble),
        )

        # Cadre des sliders EQ (10 bandes)
        bands_card = self._build_card(container, "Bandes")
        for i in range(len(self._band_vars)):
            slider, label = self._add_slider_row(
                bands_card, self.FREQUENCY_BANDS[i], self._band_vars[i],
                lambda idx=i: self._commit_band(idx),
            )
            self._sliders.append(slider)
            self._labels.append(label)

        # Cadre des presets
        presets_card = self._build_card(container, "Presets Rapides")
        preset_row = tk.Frame(presets_card, bg=theme.BG_CARD)
        preset_row.pack(fill=tk.X)
        for preset in ("flat", "bass_boost", "vocal", "gaming", "movie"):
            widgets.RoundedButton(
                preset_row,
                text=PRESET_LABELS[preset],
                command=lambda p=preset: self._apply_preset(p),
                icon="equalizer",
                bg=theme.BG_CARD,
                fill=theme.BG_CONTROL,
                fg=theme.FG_PRIMARY,
                font=theme.FONT_BODY,
                padx=16,
                pady=10,
            ).pack(side=tk.LEFT, padx=(0, 12))

        # Commande de réinitialisation
        cmd_frame = tk.Frame(container, bg=theme.BG_WINDOW)
        cmd_frame.pack(fill=tk.X, pady=(0, 20))
        widgets.RoundedButton(
            cmd_frame,
            text="Réinitialiser tout",
            command=self._reset_all,
            icon="reset",
            bg=theme.BG_WINDOW,
            fill=theme.BG_CONTROL,
            fg=theme.FG_PRIMARY,
            font=theme.FONT_BODY,
            padx=16,
            pady=10,
        ).pack(side=tk.RIGHT)

    def _build_card(self, parent, title: str) -> tk.Frame:
        """Construit une carte de section (label + cadre bordé) et retourne l'intérieur."""
        tk.Label(
            parent, text=title, bg=theme.BG_WINDOW, fg=theme.FG_LABEL,
            font=theme.FONT_LABEL, anchor="w",
        ).pack(fill=tk.X, pady=(0, 10))

        card = tk.Frame(
            parent, bg=theme.BG_CARD, highlightbackground=theme.BORDER_CARD,
            highlightthickness=1, bd=0,
        )
        card.pack(fill=tk.X, pady=(0, 20))

        inner = tk.Frame(card, bg=theme.BG_CARD)
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=18)
        return inner

    def _add_slider_row(
        self,
        parent,
        label_text: str,
        var: tk.DoubleVar,
        on_release: Callable[[], None],
    ) -> tuple[widgets.Slider, tk.Label]:
        """Construit une ligne slider horizontal + label fréquence/valeur.

        Le curseur suit le glissement (affichage local) ; l'envoi matériel
        se fait au relâchement (``on_release``) pour ne pas saturer le canal
        de contrôle HID.
        """
        row = tk.Frame(parent, bg=theme.BG_CARD)
        row.pack(fill=tk.X, pady=8)

        name_label = tk.Label(
            row, text=label_text, width=9, anchor="w",
            bg=theme.BG_CARD, fg=theme.FG_PRIMARY, font=theme.FONT_BODY,
        )
        name_label.pack(side=tk.LEFT)

        value_label = tk.Label(
            row, text=f"{var.get():+.1f} dB", width=7, anchor="center",
            bg=theme.BG_VALUE, fg=theme.FG_PRIMARY, font=theme.FONT_SMALL,
            padx=6, pady=6,
        )
        value_label.pack(side=tk.RIGHT)

        def on_drag(value: float, _label=value_label):
            _label.config(text=f"{value:+.1f} dB")

        slider = widgets.Slider(
            row, variable=var, from_=-12, to=12, step=0.5,
            on_change=on_drag, on_release=on_release, bg=theme.BG_CARD,
            width=240,
        )
        slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=12)

        return slider, value_label

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
        self._set_status(f"Preset « {PRESET_LABELS.get(preset_name, preset_name)} » appliqué")

    def _reset_all(self):
        """Réinitialise toutes les bandes à 0 dB."""
        self._apply_preset("flat")
