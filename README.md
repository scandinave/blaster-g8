# Sound Blaster G8 Control

Application de contrôle open source pour la carte son **Creative Sound Blaster G8**,
sous **macOS** et **Linux** (Windows possible via hidapi, non testé).

## État des fonctionnalités

| Fonction | État | Détail |
|---|---|---|
| **Scout Mode** | ✅ Fonctionnel | Trame validée sur le matériel, trafic USB identique à l'application Creative |
| **Direct Mode** | ✅ Fonctionnel | Trame `0x39` validée, lecture d'état + reconnexion après le reset USB de la carte |
| **Mode Sonore** | ✅ Fonctionnel | 51 modes (jeux, musique, égaliseurs génériques) reversés depuis des captures dédiées, trame `0x12` par paramètre |
| **Égaliseur 10 bandes + Préampli** | ✅ Fonctionnel | Édition manuelle par slider, trame `0x12` par bande, validée sur le matériel |
| **Basse / Aigus** | ⚠️ Approximatif | Pas de paramètre dédié sur la carte : réécrit les 10 bandes selon une courbe estimée depuis `Equalizer-manual.pcapng`, non garantie identique à Creative |
| CrystalVoice | ⛔ Non implémenté | Trame USB non encore capturée |

Les fonctions non implémentées sont grisées dans l'interface : elles ne
prétendent pas agir sur la carte tant que la trame correspondante n'a pas été
identifiée (voir *Contribuer au reverse engineering* plus bas).

## Installation

```bash
pip install -e .
```

### Linux

#### Backend hidapi : hidraw ou libusb

`pip install hidapi` installe **deux** modules Python côté Linux :

| Module | Backend | `usage_page` énuméré | Driver noyau |
|---|---|---|---|
| `hid` | **libusb** (celui des wheels binaires, donc le défaut) | ❌ toujours `0` | détache `usbhid` pendant l'accès |
| `hidraw` | **hidraw** | ✅ lu depuis sysfs | conservé |

`soundblaster_g8/hidbackend.py` **préfère `hidraw`** et se replie sur `hid`
(libusb). Le backend retenu est journalisé au démarrage et affiché par :

```bash
python tools/g8_probe.py --backend
```

Pour obtenir le module `hidraw`, il faut compiler hidapi localement :

```bash
sudo apt install libudev-dev libusb-1.0-0-dev   # ou l'équivalent de la distro
HIDAPI_WITH_HIDRAW=1 pip install --no-binary :all: hidapi
```

Conséquences du backend libusb :

- `hid_enumerate()` ne renseigne pas `usage_page` : l'interface de contrôle est
  sélectionnée sur `interface_number == 4` (chemin **normal** dans ce cas, pas
  un mode dégradé).
- libusb **détache le driver noyau** `usbhid` de l'interface le temps de
  l'accès : les touches média de la carte peuvent ne plus remonter pendant ce
  temps, et l'accès nécessite le device USB parent (voir la règle udev).

#### Droits d'accès (udev)

```bash
sudo cp udev/99-soundblaster-g8.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

La règle `KERNEL=="hidraw*"` couvre le backend hidraw, la règle
`SUBSYSTEM=="usb"` est **obligatoire pour libusb** (accès usbfs + détachement
du driver noyau). `TAG+="uaccess"` suffit pour une session locale ;
`GROUP="plugdev"` est simplement ignoré sur les distributions sans ce groupe
(Fedora, Arch...).

⚠️ **Course avec udev** : après le reset USB provoqué par une bascule du Direct
Mode, le nouveau `/dev/hidrawN` peut apparaître avant que udev n'ait appliqué
les droits. Le driver retente donc l'ouverture (`PermissionError` traitée comme
transitoire) pendant 12 secondes.

### macOS

Aucune configuration particulière : l'accès HID aux interfaces vendor est
autorisé sans privilèges élevés (backend IOKit).

## Utilisation

```bash
python main.py          # interface graphique
soundblaster-g8         # après installation
```

### Outil en ligne de commande

`tools/g8_probe.py` permet de piloter et de diagnostiquer la carte sans GUI :

```bash
python tools/g8_probe.py --backend           # backend hidapi retenu (hidraw/libusb/iokit)
python tools/g8_probe.py --list              # interfaces HID détectées
python tools/g8_probe.py --selftest          # valide l'encodage sans matériel
python tools/g8_probe.py --scout on --debug  # active le Scout Mode
python tools/g8_probe.py --scout off
python tools/g8_probe.py --direct on --debug # active le Direct Mode (reset USB)
python tools/g8_probe.py --direct-status     # lit l'état du Direct Mode
python tools/g8_probe.py --reconnect-test 5  # 5 bascules consécutives du Direct Mode
python tools/g8_probe.py --monitor           # écoute les notifications de la carte
python tools/g8_probe.py --raw 26 0702000100 # envoie une trame arbitraire
python tools/g8_probe.py --set 07:0002=1     # écrit un paramètre (feature:param=valeur)
python tools/g8_probe.py --list-sound-modes  # liste les modes sonores disponibles
python tools/g8_probe.py --sound-mode esport --debug  # applique un mode sonore
```

## Protocole USB (reversé)

La carte (VID `041e` / PID `329b`) expose deux interfaces HID :

| Interface | Usage page | Rôle |
|---|---|---|
| 3 | `0x000C` (Consumer) | touches média, rapports d'entrée de 16 o |
| **4** | **`0xFF01` (Vendor)** | **canal de contrôle**, EP `0x85` interrupt IN, rapports de 64 o |

⚠️ Ouvrir la carte avec `hid.device().open(VID, PID)` peut tomber sur
l'interface 3, qui **rejette** les commandes. Le driver sélectionne
explicitement l'interface de contrôle : `usage_page == 0xFF01`, à défaut
`interface_number == 4` (cas du backend libusb, qui n'énumère pas
`usage_page`), en dernier recours `input_report_length == 64`.

## Transport HID

L'interface 4 **n'a pas d'endpoint interrupt OUT**. Toute écriture est donc un
transfert de contrôle `SET_REPORT`, et la capture ne montre **qu'un seul**
transport, Scout Mode et Direct Mode confondus :

```
bmRequestType = 0x21   (Host→Device, Class, Interface)
bRequest      = 0x09   (SET_REPORT)
wValue        = 0x0200 (report type 0x02 = Output, report ID 0x00)
wIndex        = 4      (numéro d'interface)
wLength       = 64     (rapport complet, trame zéro-paddée)
```

Côté Python, `hid_write()` consomme le **premier octet comme report ID** : le
driver écrit donc toujours `b"\x00" + pad_report(frame)`, soit 65 octets, pour
obtenir `wValue = 0x0200` et `wLength = 64`.

```
Scout ON   : 5a 26 05 07 02 00 01 00  + 56 zéros
Direct ON  : 5a 39 03 00 05 01        + 58 zéros
```

Les trois chemins hidapi possibles :

| Backend | Ce que fait `hid_write(b"\x00" + 64 o)` | `usage_page` énuméré |
|---|---|---|
| macOS / IOKit | `IOHIDDeviceSetReport(Output, id=0, 64 o)` | ✅ |
| Linux / hidraw | `write(/dev/hidrawN)` puis repli automatique sur `HID_REQ_SET_REPORT` faute d'EP OUT | ✅ |
| Linux / libusb | détache `usbhid`, pas d'EP OUT → transfert de contrôle `SET_REPORT` direct | ❌ (toujours 0) |

Un garde-fou subsiste : si aucune réponse n'arrive avec la forme paddée, le
driver retente **une seule fois** avec l'ancienne forme (trame nue, report ID
`0x5A`, `wValue = 0x025A`) et le journalise explicitement.

### Framing

```
+------+--------+--------+------------------+
| 0x5A | type   | length | payload          |
+------+--------+--------+------------------+
```

`length` = taille du payload (en-tête de 3 octets exclu).
Le bit `0x80` dans `type` signale un rejet par la carte.

### Commande SET u16 (type `0x26`)

```
payload = <feature:1> <param:u16 LE> <valeur:u16 LE>

Scout Mode ON  : 5a 26 05 07 02 00 01 00
Scout Mode OFF : 5a 26 05 07 02 00 00 00
```

### Direct Mode (type `0x39`)

```
écriture ON    : 5a 39 03 00 05 01      -> ACK 5a 02 0a 39 00 05 01
écriture OFF   : 5a 39 03 00 05 00      -> ACK 5a 02 0a 39 00 05 00
lecture d'état : 5a 39 05 01 20 00 00 00
réponse        : 5a 39 05 01 <bits> 40 00 00   (bit 0x20 -> Direct Mode actif)
```

⚠️ L'ACK de `0x39` **n'a pas le même layout** que celui de `0x26` :
`<cmd> <status> <param> <value>` au lieu de
`<cmd> <status> <feature> <param:u16> <value:u16>`. D'où les accesseurs dédiés
`Frame.dm_ack_param` / `Frame.dm_ack_value`.

### Reset USB après bascule du Direct Mode

Le Direct Mode reconfigure la chaîne audio : **la carte se réénumère**.
Chronologie mesurée sur le pcap, à partir de l'émission de la commande `0x39` :

| Instant | Événement |
|---|---|
| +0.0002 s | ACK `5a 02 0a 39 00 05 xx` |
| +0.005 s | notifications `0x1a` puis dumps `0x11` |
| **+0.6 s** | **USB reset / disconnect** → l'ancien handle HID est mort |
| +1.3 s | le device réapparaît (nouveau `/dev/hidrawN`, nouveau `path`) |

`set_direct_mode()` enchaîne donc : purge → envoi 64 o → attente de l'ACK
(budget 300 ms) → drainage des `0x1a`/`0x11` → `reconnect()`. La reconnexion
ferme l'ancien handle, laisse 1 s de grâce, puis réénumère toutes les 250 ms
pendant 12 s au maximum et **valide chaque ouverture par un aller-retour réel**
(`5a 09 01 02` → réponse `0x09` contenant la version du firmware,
`1.2.250819.0903` sur la carte de référence) : un handle ouvert sur le nœud
moribond accepte l'`open` mais ne répond plus.

Conséquence pour l'interface : une bascule du Direct Mode prend 2 à 4 secondes.
La GUI l'exécute dans un thread de travail, désactive l'interrupteur et affiche
« reconnexion de la carte… ».

### Carte → hôte (EP `0x85`, 64 octets)

```
ACK (type 0x02)   : 5a 02 0a 26 00 07 02 00 01 00 ...
                    └ cmd 0x26, status 0x00 (OK), écho feature/param/valeur

Notification 0x1a : « un réglage a changé », émise en rafale après un 0x39

Réponse info 0x09 : contient la version du firmware en ASCII

Dump de paramètres (type 0x11) :
  5a 11 <len> <count:u16> puis N entrées de 6 octets : 96 <id> <float32 LE>
  ex. 96 05 a4 70 3d 3f  ->  param 0x05 = 0.74
      96 00 00 00 80 3f  ->  param 0x00 = 1.0
```

### Mode Sonore (type `0x12`, confirmé)

Chaque mode sonore de l'application Creative (un fichier
`Equalizer-*.pcapng` par mode dans les captures dédiées) envoie une séquence
ordonnée d'écritures **`CMD_SET_FLOAT`** :

```
payload (7 octets) = 0x01 0x96 <param_id:1> <valeur:f32 LE>

écriture bande 0x0b = -4.0 dB : 5a 12 07 01 96 0b 00 00 80 c0
ACK                           : 5a 02 0a 12 00 ...
```

`0x96` est le même marqueur TLV que celui des entrées d'un dump `0x11`
(`0x01` est un préfixe constant, rôle non identifié). Paramètres confirmés :

- param `0x00` : SBX master (0/1)
- param `0x01` : gain/compensation master
- param `0x09` : égaliseur on/off
- params `0x0b`–`0x14` : les 10 bandes de l'égaliseur, en dB
- param `0x0a` : **Préampli** (gain d'entrée, en dB)

⚠️ `0x0a` valait `0.0` dans les 51 captures de mode sonore, ce qui avait
d'abord laissé penser à un id de preset (« 0 = manuel »). La capture
`Equalizer-manual.pcapng` (variations individuelles des sliders, glissée de
`+6.1` à `-8.5`) montre que c'est en réalité un slider à part entière, au
même titre qu'une bande - simplement laissé à 0 dB par tous les modes
capturés.

D'autres paramètres apparaissent selon les modes (`0x02`, `0x04`/`0x05`,
`0x07`/`0x08`, `0x18`/`0x19`...), probablement des sous-réglages de
l'« acoustic engine » (Crystalizer, Surround...) : leur rôle exact n'est pas
identifié, mais rejouer la séquence complète capturée suffit à appliquer le
mode correctement. Aucun reset USB n'est déclenché par ces écritures.

Les séquences par mode sont générées depuis les captures par
`tools/extract_sound_modes.py` dans `soundblaster_g8/sound_modes.py` (voir
« Contribuer au reverse engineering » ci-dessous pour ajouter un mode).

### Basse / Aigus (approximatif, pas de paramètre dédié)

`Equalizer-manual.pcapng` montre que les sliders Basse et Aigus n'ont **pas**
de paramètre propre : les bouger réécrit les 10 bandes existantes
(`0x0b`-`0x14`) avec une courbe « tilt » (accentuation décroissante depuis une
extrémité du spectre, l'autre extrémité restant inchangée). `controller
.nudge_eq_tilt` applique une approximation linéaire de cette courbe,
calibrée sur les deltas mesurés dans cette capture
(`BASS_TILT_WEIGHTS`/`TREBLE_TILT_WEIGHTS` dans `controller.py`) : ce n'est
**pas garanti identique** à l'algorithme réel de Creative, faute d'une
capture paramétrique complète (plusieurs positions de slider isolées).

### Activation de l'égaliseur

`Equalizer-manual.pcapng` ne contient aucune écriture de `param 0x09` : l'app
Creative active l'égaliseur ailleurs (probablement à l'ouverture de l'onglet
EQ), pas à chaque geste sur un slider. Sans cela, les écritures de bandes
sont bien acquittées par la carte mais restent inaudibles tant que le maître
EQ est coupé (mode actif « Désactivé »). L'app active donc automatiquement
`param 0x09` (`controller.ensure_eq_enabled`) à l'entrée sur la page
Équaliseur.

## Contribuer au reverse engineering

Pour ajouter une fonction (Direct Mode, CrystalVoice, EQ...) :

1. Capturer le trafic pendant que l'application Creative officielle modifie
   **un seul** réglage :

   ```bash
   # macOS (interface XHC2 selon le port utilisé)
   tshark -i XHC2 -w reglage.pcapng -a duration:15
   # Linux
   sudo modprobe usbmon && tshark -i usbmon1 -w reglage.pcapng -a duration:15
   ```

2. Extraire les commandes émises :

   ```bash
   tshark -r reglage.pcapng -V | grep -E "CONTROL response data|Leftover Capture Data"
   ```

3. Identifier le couple `feature` / `param` dans le payload, puis le tester :

   ```bash
   python tools/g8_probe.py --set <feature>:<param>=1
   ```

4. Ajouter la constante dans `soundblaster_g8/protocol.py`, la méthode dans
   `driver.py`, et le nom de la fonction dans `SUPPORTED_FEATURES`
   (`controller.py`) pour l'activer dans la GUI.

`python tools/g8_probe.py --monitor` affiche en direct les notifications
décodées, ce qui aide à repérer les identifiants de paramètres.

Pour ajouter un mode sonore (nouveau preset EQ/acoustic engine) : capturer le
trafic pendant que l'application Creative applique **un seul** mode (même
procédure ci-dessus), déposer le `.pcapng` dans le dossier de captures, puis
régénérer `soundblaster_g8/sound_modes.py` :

```bash
python tools/extract_sound_modes.py --input /chemin/vers/le/dossier/de/captures
```

## Structure du projet

```
OpenCreativeApp/
├── main.py                      # point d'entrée GUI
├── tools/g8_probe.py            # CLI de diagnostic / reverse engineering
├── tools/extract_sound_modes.py # génère sound_modes.py depuis des captures pcap
├── udev/99-soundblaster-g8.rules
└── soundblaster_g8/
    ├── hidbackend.py            # sélection du backend hidapi (seul code par plateforme)
    ├── protocol.py              # encodage/décodage des trames (sans I/O)
    ├── sound_modes.py           # modes sonores générés (voir extract_sound_modes.py)
    ├── driver.py                # I/O HID (hidapi)
    ├── controller.py            # logique métier + événements
    └── gui/
        ├── main_window.py
        └── eq_panel.py
```

## Architecture

- **hidbackend.py** : seul module dépendant de la plateforme ; choisit
  `hidraw` / `libusb` / IOKit et expose `enumerate()`, `open_path()`,
  `backend_name()`, `provides_usage_page()`
- **protocol.py** : couche pure (framing, opcodes, TLV, padding), testable sans
  matériel via `--selftest`
- **driver.py** : sélection de l'interface HID, transport unifié (SET_REPORT
  64 o), attente et vérification de l'ACK, reconnexion après reset USB, cache
  d'état alimenté par les notifications. Toutes les I/O sont sérialisées par un
  verrou (les handles hidapi ne sont pas thread-safe)
- **controller.py** : logique métier ; les `set_*` renvoient un booléen
  indiquant si la carte a confirmé la commande ; événement `reconnecting`
- **gui/** : Tkinter ; les commandes partent dans un thread de travail et
  l'interrupteur est resynchronisé sur l'état matériel réel au retour

## Licence

MIT
