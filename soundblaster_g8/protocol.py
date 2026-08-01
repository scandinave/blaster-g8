"""
Protocole HID vendor de la Creative Sound Blaster G8.

Ce module ne fait *aucune* I/O : il encode et décode uniquement les trames.
Tout ce qui suit a été déduit de captures USB (tshark) de l'activation puis de
la désactivation du Scout Mode et du Direct Mode par l'application Creative
officielle (``DirectModeOffpcapng.pcapng``).

Topologie USB observée
----------------------
La carte expose deux interfaces HID (VID 041e / PID 329b) :

* interface 3, usage page 0x000C (Consumer)   -> touches média, input 16 o
* interface 4, usage page 0xFF01 (Vendor)     -> **canal de contrôle**,
  input 64 o (EP 0x85, interrupt IN). Le descripteur ne déclare **aucun**
  report ID et surtout **aucun endpoint interrupt OUT** :
  ``0601ff0901a101 1901 2940 1500 26ff00 7508 9540 8100 1901 2940 9100 c0``.

Sens hôte -> carte : un seul transport
--------------------------------------
Faute d'endpoint OUT, toute écriture est un transfert de **contrôle**
HID SET_REPORT. La capture montre un transport unique, y compris pour le
Scout Mode :

    bmRequestType = 0x21   (Host->Device, Class, Interface)
    bRequest      = 0x09   (SET_REPORT)
    wValue        = 0x0200 (report type 0x02 = Output, report ID 0x00)
    wIndex        = 4      (numéro d'interface)
    wLength       = 64     (taille du rapport, trame zéro-paddée)

La trame utile commence donc *dans* le rapport, par le magic 0x5A, et le
rapport est complété par des zéros jusqu'à 64 octets (:func:`pad_report`) :

    Scout ON    : 5a 26 05 07 02 00 01 00  + 56 zéros
    Scout OFF   : 5a 26 05 07 02 00 00 00  + 56 zéros
    Direct ON   : 5a 39 03 00 05 01        + 58 zéros
    Direct OFF  : 5a 39 03 00 05 00        + 58 zéros

Côté Python, ``hid_write()`` consomme le **premier octet comme report ID** :
on écrit donc ``b"\\x00" + pad_report(frame)`` (65 octets) pour obtenir
``wValue = 0x0200`` et ``wLength = 64``.

Les trois chemins hidapi possibles
----------------------------------
+----------------+-------------------------------------------------+---------------+
| Backend        | Ce que fait ``hid_write(b"\\x00" + 64 o)``        | ``usage_page``|
+================+=================================================+===============+
| macOS / IOKit  | ``IOHIDDeviceSetReport(Output, id=0, 64 o)``     | renseigné     |
+----------------+-------------------------------------------------+---------------+
| Linux / hidraw | ``write(/dev/hidrawN)``, puis repli automatique  | renseigné     |
|                | sur ``HID_REQ_SET_REPORT`` faute d'EP OUT        | (sysfs)       |
+----------------+-------------------------------------------------+---------------+
| Linux / libusb | détache ``usbhid``, pas d'EP OUT -> transfert de | **absent**    |
|                | contrôle ``SET_REPORT`` direct                   | (toujours 0)  |
+----------------+-------------------------------------------------+---------------+

Conséquence pratique : avec le backend libusb la sélection de l'interface de
contrôle ne peut pas s'appuyer sur ``usage_page`` (voir
``driver._select_control_interface``).

Sens carte -> hôte
------------------
Notifications de 64 octets sur l'endpoint interrupt IN 0x85 :

    5a 02 0a 26 00 07 02 00 01 00 ...   -> ACK de la commande 0x26, status 0x00
    5a 02 0a 39 00 05 00 ...            -> ACK de la commande 0x39, status 0x00
    5a 39 05 01 00 40 00 00 ...         -> réponse d'état du Direct Mode
    5a 1a ...                           -> notification « l'état a changé »
    5a 11 0e 02 00 96 00 <f32> ...      -> dump de paramètres
    5a 09 ... "1.2.250819.0903"         -> réponse d'info / firmware

Reset USB après une bascule du Direct Mode
------------------------------------------
Le Direct Mode reconfigure la chaîne audio : la carte se **réénumère**. La
chronologie du pcap, à partir de l'émission de la commande 0x39 :

    +0.0002 s : ACK 5a 02 0a 39 00 ...
    +0.005  s : notifications 0x1a puis dumps 0x11
    +0.6    s : USB reset / disconnect -> l'ancien handle HID est mort
    +1.3    s : le device réapparaît (nouveau /dev/hidrawN, nouveau path)

Toute écriture sur l'ancien handle après +0.6 s échoue. Le driver doit donc
fermer, attendre, puis réénumérer et rouvrir (``driver.reconnect``).

Framing commun
--------------
    +------+--------+--------+-----------------+
    | 0x5A | type   | length | payload         |
    +------+--------+--------+-----------------+
       0       1        2       3 .. 3+length

``length`` est la taille du payload (en-tête de 3 octets exclu). Le bit 0x80
positionné dans ``type`` signale une erreur (observé lorsque la carte reçoit
une trame invalide : ``5a 11 80 0e ...``).

Payload d'une commande SET u16 (type 0x26)
------------------------------------------
    +---------+-----------+----------+
    | feature | param u16 | value u16|
    +---------+-----------+----------+
       0x07      0x0002      0/1        (Scout Mode)

Payload d'un ACK de 0x26 (type 0x02)
------------------------------------
    <cmd echo> <status> <feature> <param u16> <value u16>
    0x26        0x00     0x07      0x0002      0x0001

Payload d'un ACK de 0x39 (type 0x02) - layout **différent**
-----------------------------------------------------------
    <cmd echo> <status> <param> <value>
    0x39        0x00     0x05    0x00        (Direct Mode OFF acquitté)

D'où les accesseurs dédiés :attr:`Frame.dm_ack_param` /
:attr:`Frame.dm_ack_value` : décoder cet ACK avec le layout de 0x26 donne un
``param`` et une ``value`` faux.

Payload d'une commande / réponse Direct Mode (type 0x39)
--------------------------------------------------------
    écriture : <feature 0x00> <param 0x05> <value 0/1>
    lecture  : requête  01 20 00 00 00
               réponse  01 00 40 00 00   -> bit 0x20 de payload[1] = activé

Payload d'un dump de paramètres (type 0x11)
-------------------------------------------
    <count u16> puis ``count`` entrées de 6 octets :
    <0x96> <param id> <valeur float32 little endian>

    ex. ``96 05 a4 70 3d 3f`` -> param 0x05 = 0.74
        ``96 00 00 00 80 3f`` -> param 0x00 = 1.0

Payload d'une commande SET FLOAT (type 0x12) - confirmé par les captures
« Sound Mode »
-------------------------------------------------------------------------
    +------+------+----------+-----------------+
    | 0x01 | 0x96 | param id | valeur f32 LE    |
    +------+------+----------+-----------------+

``0x96`` est le même marqueur TLV que celui des entrées d'un dump de
paramètres (type 0x11) : une écriture ``0x12`` a donc la même forme qu'une
entrée de lecture, préfixée par ``0x01`` (rôle non identifié - constant dans
toutes les captures observées, laissé tel quel).

    param 0x00        : SBX master (0/1)
    param 0x01        : gain/compensation master
    param 0x09        : égaliseur on/off (0/1)
    params 0x0b..0x14 : les 10 bandes de l'égaliseur, en dB
    param 0x0a        : preset d'égaliseur (0 = manuel, constant observé)

Un « mode sonore » de l'application Creative (un fichier ``Equalizer-*.pcapng``
par mode dans les captures fournies) est une séquence ordonnée de ces
écritures ``0x12`` ; l'ACK carte est ``5a 02 0a 12 00 ...``
(``Frame.ack_command``/``Frame.ack_status``/``Frame.ack_ok`` suffisent, le
layout de l'ACK ne suit pas celui de ``0x26``). Aucun reset USB n'est
déclenché par ces écritures. Voir :mod:`soundblaster_g8.sound_modes` pour les
séquences extraites des captures et :func:`build_set_float` pour
l'encodage.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Optional

# --- Constantes de framing ---------------------------------------------------

MAGIC = 0x5A  # 1er octet de toute trame
HEADER_SIZE = 3  # magic + type + length
ERROR_FLAG = 0x80  # bit positionné dans le champ "type" en cas d'erreur

#: Taille d'un rapport HID sur l'interface de contrôle (in comme out).
REPORT_SIZE = 64

#: Report ID utilisé dans ``wValue`` : 0x00 -> wValue = 0x0200.
REPORT_ID = 0x00

#: Report ID historique (wValue = 0x025A), conservé pour le repli de secours.
LEGACY_REPORT_ID = 0x5A

# Types de trames hôte -> carte
CMD_SET = 0x26  # écriture d'un paramètre u16
CMD_DIRECT_MODE = 0x39  # écriture / lecture du Direct Mode
CMD_INFO = 0x09  # interrogation d'identité (firmware) - utilisé comme sonde
CMD_SET_FLOAT = 0x12  # écriture d'un float32 (documenté, non utilisé)

# Types de trames carte -> hôte
NOTIF_ACK = 0x02  # accusé de réception d'une commande
NOTIF_PARAMS = 0x11  # dump de paramètres (TLV float)
NOTIF_STATE_CHANGED = 0x1A  # « un réglage a changé », émis en rafale après 0x39

# Marqueur d'une entrée TLV dans un dump de paramètres
TLV_FLOAT = 0x96

# Statuts d'ACK
STATUS_OK = 0x00

# --- Identifiants de fonctionnalités ----------------------------------------
# Scout Mode et Direct Mode sont confirmés par les captures. Les autres
# fonctions (CrystalVoice, égaliseur) nécessitent une capture USB dédiée avant
# de pouvoir être ajoutées ici (voir « Pistes non implémentées »).

FEATURE_SCOUT = 0x07
PARAM_SCOUT_ENABLED = 0x0002

#: (feature, param) confirmés par l'analyse du pcap
SCOUT_MODE = (FEATURE_SCOUT, PARAM_SCOUT_ENABLED)

# Direct Mode - identifiants extraits des captures USB
FEATURE_DIRECT_MODE = 0x00
PARAM_DIRECT_MODE = 0x05

# Mode sonore / égaliseur - identifiants de paramètres extraits des captures
# « Sound Mode » (commande CMD_SET_FLOAT, type 0x12).
PARAM_SBX_MASTER = 0x00  # SBX master (0/1)
PARAM_MASTER_GAIN = 0x01  # gain/compensation master
PARAM_EQ_ENABLED = 0x09  # égaliseur on/off (0/1)
PARAM_EQ_PRESET = 0x0A  # preset d'égaliseur (0 = manuel)
EQ_BAND_PARAMS = tuple(range(0x0B, 0x15))  # les 10 bandes, en dB

#: Préfixe constant observé dans toutes les écritures SET FLOAT.
SET_FLOAT_PREFIX = 0x01

#: Payload de la requête d'état du Direct Mode (type 0x39).
DIRECT_MODE_STATUS_PAYLOAD = b"\x01\x20\x00\x00\x00"

#: Bit du 2e octet de payload de la réponse d'état indiquant « Direct Mode actif ».
DIRECT_MODE_STATUS_BIT = 0x20

#: Payload de la sonde d'identité (``5a 09 01 02``).
INFO_PROBE_PAYLOAD = b"\x02"


# --- Structures de décodage --------------------------------------------------


@dataclass(frozen=True)
class ParamEntry:
    """Une entrée TLV d'un dump de paramètres (type 0x11)."""

    kind: int  # normalement TLV_FLOAT (0x96)
    param_id: int
    raw: bytes  # 4 octets bruts

    @property
    def as_float(self) -> float:
        return struct.unpack("<f", self.raw)[0]

    @property
    def as_int(self) -> int:
        return int.from_bytes(self.raw, "little")

    def __str__(self) -> str:  # pragma: no cover - affichage debug
        return f"0x{self.param_id:02x}={self.as_float:g} (raw={self.raw.hex()})"


@dataclass(frozen=True)
class Frame:
    """Une trame décodée du protocole G8."""

    frame_type: int
    length: int
    payload: bytes
    raw: bytes

    # --- Nature de la trame ---
    @property
    def is_error(self) -> bool:
        """Le bit 0x80 du champ type signale un rejet par la carte."""
        return bool(self.frame_type & ERROR_FLAG)

    @property
    def base_type(self) -> int:
        """Type de trame sans le bit d'erreur."""
        return self.frame_type & ~ERROR_FLAG

    @property
    def is_ack(self) -> bool:
        return self.base_type == NOTIF_ACK

    @property
    def is_params(self) -> bool:
        return self.base_type == NOTIF_PARAMS

    @property
    def is_state_changed(self) -> bool:
        return self.base_type == NOTIF_STATE_CHANGED

    # --- Décodage d'un ACK (type 0x02) ---
    @property
    def ack_command(self) -> Optional[int]:
        return self.payload[0] if len(self.payload) >= 1 else None

    @property
    def ack_status(self) -> Optional[int]:
        return self.payload[1] if len(self.payload) >= 2 else None

    @property
    def ack_ok(self) -> bool:
        return (not self.is_error) and self.ack_status == STATUS_OK

    @property
    def ack_feature(self) -> Optional[int]:
        """Feature échoée - valable pour l'ACK de 0x26 uniquement."""
        return self.payload[2] if len(self.payload) >= 3 else None

    @property
    def ack_param(self) -> Optional[int]:
        """Param u16 échoé - valable pour l'ACK de 0x26 uniquement."""
        if len(self.payload) < 5:
            return None
        return int.from_bytes(self.payload[3:5], "little")

    @property
    def ack_value(self) -> Optional[int]:
        """Valeur échoée sur 2 octets - valable pour l'ACK de 0x26 uniquement."""
        if len(self.payload) < 7:
            return None
        return int.from_bytes(self.payload[5:7], "little")

    # --- Décodage d'un ACK de commande 0x39 (layout différent de 0x26) ---
    @property
    def dm_ack_param(self) -> Optional[int]:
        """Param échoé dans un ACK de 0x39 : ``5a 02 0a 39 00 [05] 00``."""
        return self.payload[2] if len(self.payload) >= 3 else None

    @property
    def dm_ack_value(self) -> Optional[int]:
        """Valeur échoée dans un ACK de 0x39 : ``5a 02 0a 39 00 05 [00]``."""
        return self.payload[3] if len(self.payload) >= 4 else None

    # --- Décodage d'une réponse d'état du Direct Mode (type 0x39) ---
    @property
    def direct_mode_enabled(self) -> Optional[bool]:
        """État du Direct Mode dans une réponse ``5a 39 05 01 <bits> ...``."""
        if self.base_type != CMD_DIRECT_MODE or len(self.payload) < 2:
            return None
        return bool(self.payload[1] & DIRECT_MODE_STATUS_BIT)

    # --- Décodage d'un dump de paramètres (type 0x11) ---
    @property
    def params(self) -> list[ParamEntry]:
        return parse_params(self.payload) if self.is_params else []

    # --- Décodage d'une réponse d'info (type 0x09) ---
    @property
    def info_text(self) -> Optional[str]:
        """Chaîne ASCII contenue dans une réponse 0x09 (version du firmware)."""
        if self.base_type != CMD_INFO:
            return None
        printable = bytes(b for b in self.payload if 0x20 <= b < 0x7F)
        return printable.decode("ascii", "ignore") or None

    def describe(self) -> str:
        """Résumé lisible, utilisé par l'outil de debug et les logs."""
        flag = " [ERREUR]" if self.is_error else ""
        if self.is_ack:
            if self.ack_command == CMD_DIRECT_MODE:
                return (
                    f"ACK{flag} cmd=0x39 status=0x{(self.ack_status or 0):02x} "
                    f"param=0x{(self.dm_ack_param or 0):02x} "
                    f"value={self.dm_ack_value}"
                )
            if self.ack_value is None:
                return f"ACK{flag} payload={self.payload.hex()}"
            return (
                f"ACK{flag} cmd=0x{self.ack_command:02x} "
                f"status=0x{self.ack_status:02x} "
                f"feature=0x{self.ack_feature:02x} "
                f"param=0x{self.ack_param:04x} "
                f"value={self.ack_value}"
            )
        if self.is_params:
            entries = ", ".join(str(p) for p in self.params)
            return f"PARAMS{flag} ({len(self.params)}) {entries}"
        if self.is_state_changed:
            return f"STATE_CHANGED{flag} payload={self.payload.hex()}"
        if self.base_type == CMD_DIRECT_MODE:
            return (
                f"DIRECT_MODE{flag} enabled={self.direct_mode_enabled} "
                f"payload={self.payload.hex()}"
            )
        if self.base_type == CMD_INFO:
            return f"INFO{flag} text={self.info_text!r} payload={self.payload.hex()}"
        return f"type=0x{self.frame_type:02x}{flag} payload={self.payload.hex()}"


@dataclass
class DecodedState:
    """Cache d'état alimenté par les notifications reçues."""

    params: dict[int, float] = field(default_factory=dict)
    features: dict[tuple[int, int], int] = field(default_factory=dict)

    def apply(self, frame: Frame) -> None:
        if frame.is_error:
            return
        if frame.is_params:
            for entry in frame.params:
                self.params[entry.param_id] = entry.as_float
        elif frame.is_ack and frame.ack_ok:
            if frame.ack_command == CMD_DIRECT_MODE:
                param, value = frame.dm_ack_param, frame.dm_ack_value
                if param is not None and value is not None:
                    self.features[(FEATURE_DIRECT_MODE, param)] = value
                return
            feature, param, value = frame.ack_feature, frame.ack_param, frame.ack_value
            if feature is not None and param is not None and value is not None:
                self.features[(feature, param)] = value


# --- Encodage ----------------------------------------------------------------


def pad_report(frame: bytes, size: int = REPORT_SIZE) -> bytes:
    """Complète une trame par des zéros jusqu'à la taille d'un rapport HID.

    L'interface 4 n'a pas d'endpoint OUT : l'écriture part en SET_REPORT avec
    ``wLength = 64``, la trame doit donc être zéro-paddée comme le fait
    l'application officielle.

    >>> pad_report(b"\\x5a\\x39\\x03\\x00\\x05\\x01")[:6].hex()
    '5a3903000501'
    >>> len(pad_report(b"\\x5a\\x39\\x03\\x00\\x05\\x01"))
    64
    """
    if len(frame) > size:
        raise ValueError(f"trame trop longue pour un rapport de {size} octets: {len(frame)}")
    return bytes(frame) + bytes(size - len(frame))


def build_frame(frame_type: int, payload: bytes) -> bytes:
    """Construit une trame ``5a <type> <len> <payload>`` (sans padding).

    Le padding à 64 octets et le préfixe de report ID sont ajoutés par la
    couche transport (:meth:`driver.SoundBlasterG8Driver._send_raw`).
    """
    if not 0 <= frame_type <= 0xFF:
        raise ValueError(f"type de trame invalide: {frame_type}")
    if len(payload) > 0xFF:
        raise ValueError(f"payload trop long: {len(payload)} octets")
    return bytes([MAGIC, frame_type, len(payload)]) + bytes(payload)


def build_set_u16(feature: int, param: int, value: int) -> bytes:
    """Construit une commande SET (type 0x26) avec une valeur sur 16 bits.

    >>> build_set_u16(FEATURE_SCOUT, PARAM_SCOUT_ENABLED, 1).hex()
    '5a26050702000100'
    """
    payload = bytes([feature]) + param.to_bytes(2, "little") + value.to_bytes(2, "little")
    return build_frame(CMD_SET, payload)


def build_set_bool(feature: int, param: int, enabled: bool) -> bytes:
    """Commande SET d'un booléen (Scout Mode, etc.)."""
    return build_set_u16(feature, param, 1 if enabled else 0)


def build_scout_mode(enabled: bool) -> bytes:
    """Trame d'activation/désactivation du Scout Mode.

    >>> build_scout_mode(True).hex()
    '5a26050702000100'
    >>> build_scout_mode(False).hex()
    '5a26050702000000'
    """
    return build_set_bool(*SCOUT_MODE, enabled)


def build_direct_mode(enabled: bool) -> bytes:
    """Trame d'activation/désactivation du Direct Mode (non paddée).

    >>> build_direct_mode(True).hex()
    '5a3903000501'
    >>> build_direct_mode(False).hex()
    '5a3903000500'
    """
    payload = bytes([FEATURE_DIRECT_MODE, PARAM_DIRECT_MODE, 1 if enabled else 0])
    return build_frame(CMD_DIRECT_MODE, payload)


def build_set_float(param: int, value: float) -> bytes:
    """Construit une commande SET FLOAT (type 0x12) - mode sonore / égaliseur.

    >>> build_set_float(PARAM_EQ_ENABLED, 1.0).hex()
    '5a12070196090000803f'
    >>> build_set_float(0x0b, -4.0).hex()
    '5a120701960b000080c0'
    """
    payload = (
        bytes([SET_FLOAT_PREFIX, TLV_FLOAT, param]) + struct.pack("<f", value)
    )
    return build_frame(CMD_SET_FLOAT, payload)


def build_direct_mode_status() -> bytes:
    """Trame de lecture de l'état du Direct Mode.

    >>> build_direct_mode_status().hex()
    '5a39050120000000'
    """
    return build_frame(CMD_DIRECT_MODE, DIRECT_MODE_STATUS_PAYLOAD)


def build_info_probe() -> bytes:
    """Trame d'interrogation d'identité, utilisée comme sonde après un reset.

    >>> build_info_probe().hex()
    '5a090102'
    """
    return build_frame(CMD_INFO, INFO_PROBE_PAYLOAD)


# --- Décodage ----------------------------------------------------------------


def parse_frame(data: bytes) -> Optional[Frame]:
    """Décode une trame reçue. Retourne None si le buffer n'est pas exploitable.

    Les rapports reçus sont toujours de 64 octets, complétés par des zéros :
    le champ ``length`` sert donc à isoler le payload utile.
    """
    if not data:
        return None

    buf = bytes(data)

    # Certains back-ends hidapi préfixent le report ID (0x00 quand les rapports
    # ne sont pas numérotés) : on se resynchronise sur le magic 0x5A.
    if buf[0] != MAGIC:
        idx = buf.find(bytes([MAGIC]))
        if idx == -1:
            return None
        buf = buf[idx:]

    if len(buf) < HEADER_SIZE:
        return None

    frame_type = buf[1]
    length = buf[2]
    payload = buf[HEADER_SIZE:HEADER_SIZE + length]
    return Frame(frame_type=frame_type, length=length, payload=payload, raw=buf)


def parse_params(payload: bytes) -> list[ParamEntry]:
    """Décode le payload d'un dump de paramètres (type 0x11)."""
    if len(payload) < 2:
        return []

    count = int.from_bytes(payload[0:2], "little")
    entries: list[ParamEntry] = []
    offset = 2
    # On borne par le buffer réellement disponible : le compteur annoncé n'est
    # pas toujours cohérent avec la taille du rapport.
    while len(entries) < count and offset + 6 <= len(payload):
        kind = payload[offset]
        param_id = payload[offset + 1]
        raw = payload[offset + 2:offset + 6]
        entries.append(ParamEntry(kind=kind, param_id=param_id, raw=raw))
        offset += 6
    return entries
