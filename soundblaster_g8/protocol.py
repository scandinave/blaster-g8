"""
Protocole HID vendor de la Creative Sound Blaster G8.

Ce module ne fait *aucune* I/O : il encode et décode uniquement les trames.
Tout ce qui suit a été déduit d'une capture USB (tshark, interface XHC2) de
l'activation puis de la désactivation du Scout Mode par l'application Creative
officielle.

Topologie USB observée
----------------------
La carte expose deux interfaces HID (VID 041e / PID 329b) :

* interface 3, usage page 0x000C (Consumer)   -> touches média, input 16 o
* interface 4, usage page 0xFF01 (Vendor)     -> **canal de contrôle**,
  input 64 o (EP 0x85, interrupt IN), output 64 o, aucun report ID déclaré
  dans le descripteur (0601ff0901a101 1901 2940 1500 26ff00 7508 9540 8100
  1901 2940 9100 c0).

Sens hôte -> carte
------------------
L'application officielle n'écrit *pas* sur un endpoint interrupt OUT : elle
émet un transfert de contrôle HID SET_REPORT :

    bmRequestType = 0x21 (Host->Device, Class, Interface)
    bRequest      = 0x09 (SET_REPORT)
    wValue        = 0x025A (report type 0x02 = Output, report ID 0x5A)
    wIndex        = 4      (numéro d'interface)
    wLength       = 8

    Scout ON  : 5a 26 05 07 02 00 01 00
    Scout OFF : 5a 26 05 07 02 00 00 00

C'est exactement ce que produit ``hid_write()`` de hidapi lorsque le premier
octet du buffer vaut 0x5A :

* macOS  : ``IOHIDDeviceSetReport(kIOHIDReportTypeOutput, reportID=0x5A, buf)``
* Linux  : hidraw -> pas d'endpoint OUT sur l'interface -> repli automatique
  sur ``HID_REQ_SET_REPORT`` avec ``wValue = (0x02 << 8) | 0x5A``.

Sens carte -> hôte
------------------
Notifications de 64 octets sur l'endpoint interrupt IN 0x85 :

    5a 02 0a 26 00 07 02 00 01 00 ...   -> ACK de la commande 0x26, status 0x00
    5a 11 0e 02 00 96 00 <f32> 96 09 <f32> ...  -> dump de paramètres

Framing commun
--------------
    +------+--------+--------+-----------------+
    | 0x5A | type   | length | payload         |
    +------+--------+--------+-----------------+
       0       1        2       3 .. 3+length

``length`` est la taille du payload (en-tête de 3 octets exclu). Le bit 0x80
positionné dans ``type`` signale une erreur (observé lorsque la carte reçoit
une trame invalide : ``5a 11 80 0e ...``).

Payload d'une commande SET (type 0x26)
--------------------------------------
    +---------+-----------+----------+
    | feature | param u16 | value u16|
    +---------+-----------+----------+
       0x07      0x0002      0/1        (Scout Mode)

Payload d'un ACK (type 0x02)
----------------------------
    <cmd echo> <status> <feature> <param u16> <value ...>
    0x26        0x00     0x07      0x0002      0x0001

Payload d'un dump de paramètres (type 0x11)
-------------------------------------------
    <count u16> puis ``count`` entrées de 6 octets :
    <0x96> <param id> <valeur float32 little endian>

    ex. ``96 05 a4 70 3d 3f`` -> param 0x05 = 0.74
        ``96 00 00 00 80 3f`` -> param 0x00 = 1.0
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Optional

# --- Constantes de framing ---------------------------------------------------

MAGIC = 0x5A  # 1er octet de toute trame, et report ID utilisé dans wValue
HEADER_SIZE = 3  # magic + type + length
ERROR_FLAG = 0x80  # bit positionné dans le champ "type" en cas d'erreur

# Types de trames hôte -> carte
CMD_SET = 0x26  # écriture d'un paramètre

# Types de trames carte -> hôte
NOTIF_ACK = 0x02  # accusé de réception d'une commande
NOTIF_PARAMS = 0x11  # dump de paramètres (TLV float)

# Marqueur d'une entrée TLV dans un dump de paramètres
TLV_FLOAT = 0x96

# Statuts d'ACK
STATUS_OK = 0x00

# --- Identifiants de fonctionnalités ----------------------------------------
# Seul le Scout Mode est confirmé par la capture. Les autres fonctions
# (Direct Mode, CrystalVoice, égaliseur) nécessitent une capture USB dédiée
# avant de pouvoir être ajoutées ici.

FEATURE_SCOUT = 0x07
PARAM_SCOUT_ENABLED = 0x0002

#: (feature, param) confirmés par l'analyse du pcap
SCOUT_MODE = (FEATURE_SCOUT, PARAM_SCOUT_ENABLED)


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
        return self.payload[2] if len(self.payload) >= 3 else None

    @property
    def ack_param(self) -> Optional[int]:
        if len(self.payload) < 5:
            return None
        return int.from_bytes(self.payload[3:5], "little")

    @property
    def ack_value(self) -> Optional[int]:
        """Valeur renvoyée en écho (2 octets utiles observés)."""
        if len(self.payload) < 7:
            return None
        return int.from_bytes(self.payload[5:7], "little")

    # --- Décodage d'un dump de paramètres (type 0x11) ---
    @property
    def params(self) -> list[ParamEntry]:
        return parse_params(self.payload) if self.is_params else []

    def describe(self) -> str:
        """Résumé lisible, utilisé par l'outil de debug et les logs."""
        flag = " [ERREUR]" if self.is_error else ""
        if self.is_ack:
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
            feature, param, value = frame.ack_feature, frame.ack_param, frame.ack_value
            if feature is not None and param is not None and value is not None:
                self.features[(feature, param)] = value


# --- Encodage ----------------------------------------------------------------


def build_frame(frame_type: int, payload: bytes) -> bytes:
    """Construit une trame ``5a <type> <len> <payload>``.

    Le buffer retourné commence par 0x5A : hidapi l'utilise comme report ID,
    ce qui produit ``wValue = 0x025A`` comme l'application officielle.
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
