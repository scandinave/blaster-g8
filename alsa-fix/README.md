# Sound Blaster G8 — ALSA Fix

Correctif automatique pour le microphone (« External Mic ») qui ne fonctionne pas
au démarrage sur Linux.

Le pilote noyau `snd-usb-audio` n'initialise pas la bonne source de capture par
défaut pour la G8 : le contrôle ALSA « PCM Capture Source » démarre sur `Line In`
au lieu de `External Mic`. Le micro ne fonctionne donc pas tant qu'on n'a pas
changé la source manuellement (alsamixer/pavucontrol), à chaque redémarrage.

Même bug, même correctif que sur la [SoundBlasterX G6](../../linuxblaster_control/alsa-fix)
(même puce/même layout de contrôles ALSA) — ce dossier en est un portage.

## Le correctif

Une règle udev détecte l'apparition de la carte ALSA de la G8 et lance
automatiquement un petit script qui sélectionne `External Mic` comme source de
capture (`PCM Capture Source`).

Fonctionne sur n'importe quelle distro. Seul `alsa-utils` (`amixer`) est requis,
déjà installé sur pratiquement tous les systèmes Linux avec du son.

Contrairement au script de la G6, celui-ci **ne coupe pas** les autres entrées de
capture (Line In / S/PDIF In / What U Hear) : il se contente de sélectionner la
bonne source.

Deux différences volontaires avec le script de la G6, pour plus de robustesse :

1. **Découverte de la carte** : lecture de `/proc/asound/card*/usbid` (fourni par
   le noyau, jamais localisé) plutôt que de parser la sortie de `aplay -l`, qui
   est localisée (`carte 1 : ...` en français au lieu de `card 1: ...`) — le
   script G6 casse silencieusement sur toute machine non anglophone.
2. **Ciblage du contrôle** : par nom (`amixer sset 'PCM Capture Source'
   'External Mic'`) plutôt que par `numid` (`cset numid=29 ...`), qui peut se
   renuméroter d'une version de pilote/noyau à l'autre.

L'application `soundblaster_g8` (GUI) réapplique aussi ce correctif à chaque
démarrage (`soundblaster_g8/alsa_fix.py`), indépendamment de ce dossier — les deux
mécanismes sont redondants par sécurité : celui-ci fonctionne même si l'app n'est
jamais lancée.

## Installation

```bash
sudo ./install.sh
```

Rebranchez la carte (ou déclenchez `sudo udevadm trigger --subsystem-match=sound`)
et le micro fonctionne.

## Désinstallation

```bash
sudo ./install.sh --uninstall
```

## Fonctionnement

```
G8 branchée
  → le noyau charge snd-usb-audio
    → ALSA enregistre la carte son
      → udev voit l'évènement SUBSYSTEM=="sound" avec l'ID USB de la G8
        → lance le script de correctif
          → amixer sélectionne "External Mic" comme source de capture
```

Aucun service, aucun démon, aucun polling. Juste un script one-shot déclenché par
la détection matérielle.
