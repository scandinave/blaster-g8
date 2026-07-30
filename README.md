# Sound Blaster G8 Control

Application de contrôle open source pour la carte son **Creative Sound Blaster G8**,
sous **macOS** et **Linux** (Windows possible via hidapi, non testé).

## État des fonctionnalités

| Fonction | État | Détail |
|---|---|---|
| **Scout Mode** | ✅ Fonctionnel | Trame validée sur le matériel, trafic USB identique à l'application Creative |
| Direct Mode | ⛔ Non implémenté | Trame USB non encore capturée |
| CrystalVoice | ⛔ Non implémenté | Trame USB non encore capturée |
| Égaliseur 10 bandes | ⛔ Non implémenté | Interface présente, mais aucune commande envoyée à la carte |

Les fonctions non implémentées sont grisées dans l'interface : elles ne
prétendent pas agir sur la carte tant que la trame correspondante n'a pas été
identifiée (voir *Contribuer au reverse engineering* plus bas).

## Installation

```bash
pip install -e .
```

### Linux : droits d'accès

hidapi passe par `/dev/hidrawX`, il faut donc installer la règle udev fournie :

```bash
sudo cp udev/99-soundblaster-g8.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

### macOS

Aucune configuration particulière : l'accès HID aux interfaces vendor est
autorisé sans privilèges élevés.

## Utilisation

```bash
python main.py          # interface graphique
soundblaster-g8         # après installation
```

### Outil en ligne de commande

`tools/g8_probe.py` permet de piloter et de diagnostiquer la carte sans GUI :

```bash
python tools/g8_probe.py --list              # interfaces HID détectées
python tools/g8_probe.py --selftest          # valide l'encodage sans matériel
python tools/g8_probe.py --scout on --debug  # active le Scout Mode
python tools/g8_probe.py --scout off
python tools/g8_probe.py --monitor           # écoute les notifications de la carte
python tools/g8_probe.py --raw 26 0702000100 # envoie une trame arbitraire
python tools/g8_probe.py --set 07:0002=1     # écrit un paramètre (feature:param=valeur)
```

## Protocole USB (reversé)

La carte (VID `041e` / PID `329b`) expose deux interfaces HID :

| Interface | Usage page | Rôle |
|---|---|---|
| 3 | `0x000C` (Consumer) | touches média, rapports d'entrée de 16 o |
| **4** | **`0xFF01` (Vendor)** | **canal de contrôle**, EP `0x85` interrupt IN, rapports de 64 o |

⚠️ Ouvrir la carte avec `hid.device().open(VID, PID)` peut tomber sur
l'interface 3, qui **rejette** les commandes. Le driver sélectionne
explicitement l'interface de usage page `0xFF01`.

### Hôte → carte : transfert de contrôle SET_REPORT

Les commandes ne passent **pas** par un endpoint interrupt OUT :

```
bmRequestType = 0x21   (Host→Device, Class, Interface)
bRequest      = 0x09   (SET_REPORT)
wValue        = 0x025A (report type 0x02 = Output, report ID 0x5A)
wIndex        = 4      (numéro d'interface)
wLength       = 8
```

C'est exactement ce que produit `hid_write()` quand le premier octet du buffer
vaut `0x5A` (macOS : `IOHIDDeviceSetReport` ; Linux : hidraw se replie sur
`HID_REQ_SET_REPORT` faute d'endpoint OUT).

### Framing

```
+------+--------+--------+------------------+
| 0x5A | type   | length | payload          |
+------+--------+--------+------------------+
```

`length` = taille du payload (en-tête de 3 octets exclu).
Le bit `0x80` dans `type` signale un rejet par la carte.

### Commande SET (type `0x26`)

```
payload = <feature:1> <param:u16 LE> <valeur:u16 LE>

Scout Mode ON  : 5a 26 05 07 02 00 01 00
Scout Mode OFF : 5a 26 05 07 02 00 00 00
```

### Carte → hôte (EP `0x85`, 64 octets)

```
ACK (type 0x02)   : 5a 02 0a 26 00 07 02 00 01 00 ...
                    └ cmd 0x26, status 0x00 (OK), écho feature/param/valeur

Dump de paramètres (type 0x11) :
  5a 11 <len> <count:u16> puis N entrées de 6 octets : 96 <id> <float32 LE>
  ex. 96 05 a4 70 3d 3f  ->  param 0x05 = 0.74
      96 00 00 00 80 3f  ->  param 0x00 = 1.0
```

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

## Structure du projet

```
OpenCreativeApp/
├── main.py                      # point d'entrée GUI
├── tools/g8_probe.py            # CLI de diagnostic / reverse engineering
├── udev/99-soundblaster-g8.rules
└── soundblaster_g8/
    ├── protocol.py              # encodage/décodage des trames (sans I/O)
    ├── driver.py                # I/O HID (hidapi)
    ├── controller.py            # logique métier + événements
    └── gui/
        ├── main_window.py
        └── eq_panel.py
```

## Architecture

- **protocol.py** : couche pure (framing, opcodes, TLV), testable sans matériel
  via `--selftest`
- **driver.py** : sélection de l'interface HID, envoi des trames, attente et
  vérification de l'ACK, cache d'état alimenté par les notifications
- **controller.py** : logique métier ; les `set_*` renvoient un booléen
  indiquant si la carte a confirmé la commande
- **gui/** : Tkinter ; un interrupteur revient à son état précédent si la carte
  n'acquitte pas

## Licence

MIT
