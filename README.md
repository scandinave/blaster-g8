# Sound Blaster G8 Control

Application graphique de contrôle pour la carte son **Creative Sound Blaster G8**.

## Fonctionnalités

- **Direct Mode**: Active/désactive le mode direct (sans traitement du signal)
- **Scout Mode**: Active/désactive le mode Scout (détecte les sons dans le jeu)
- **CrystalVoice**: Active/désactive CrystalVoice (optimisation de la voix en jeu)
- **Égaliseur 10 bandes**: Interface dédiée pour régler chaque bande de fréquence (-12dB à +12dB)

## Installation

```bash
pip install -e .
```

Ou directement:

```bash
pip install .
```

## Utilisation

### Lancer l'application

```bash
python main.py
```

Ou après installation:

```bash
soundblaster-g8
```

## Structure du projet

```
OpenCreativeApp/
├── pyproject.toml        # Configuration du package
├── main.py               # Point d'entrée
└── soundblaster_g8/      # Package principal
    ├── __init__.py
    ├── driver.py         # Mock driver (printf)
    ├── controller.py     # Logique métier
    └── gui/              # Interface Tkinter
        ├── __init__.py
        ├── main_window.py    # Fenêtre principale
        └── eq_panel.py       # Panneau égaliseur
```

## Architecture

- **driver.py**: Classe `SoundBlasterG8Driver` qui simule les appels matériels via `print()`
- **controller.py**: Classe `SoundBlasterController` avec la logique métier et événements
- **gui/main_window.py**: Fenêtre principale Tkinter avec contrôles
- **gui/eq_panel.py**: Panneau d'égaliseur à 10 bandes avec sliders

## Presets EQ disponibles

- **flat**: Toutes bandes à 0dB (plat)
- **bass_boost**: Renforcement des basses
- **vocal**: Optimisé pour la voix
- **gaming**: Optimisé pour le gaming
- **movie**: Profil cinématique

## Développement

Pour développer avec pip en mode édition:

```bash
pip install -e .
```

Les modifications dans le code seront immédiatement appliquées.

## Licence

MIT