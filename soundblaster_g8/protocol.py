"""
Creative Sound Blaster G8 vendor HID protocol.

This module does *no* I/O: it only encodes and decodes frames. Everything
below was deduced from USB captures (tshark) of the official Creative
application turning Scout Mode and Direct Mode on then off
(``DirectModeOffpcapng.pcapng``).

Observed USB topology
----------------------
The card exposes two HID interfaces (VID 041e / PID 329b):

* interface 3, usage page 0x000C (Consumer)   -> media keys, 16 B input
* interface 4, usage page 0xFF01 (Vendor)     -> **control channel**,
  64 B input (EP 0x85, interrupt IN). The descriptor declares **no**
  report ID and, notably, **no interrupt OUT endpoint**:
  ``0601ff0901a101 1901 2940 1500 26ff00 7508 9540 8100 1901 2940 9100 c0``.

Host -> card direction: a single transport
--------------------------------------
With no OUT endpoint, every write is a HID **control** transfer
(SET_REPORT). The capture shows a single transport, including for Scout
Mode:

    bmRequestType = 0x21   (Host->Device, Class, Interface)
    bRequest      = 0x09   (SET_REPORT)
    wValue        = 0x0200 (report type 0x02 = Output, report ID 0x00)
    wIndex        = 4      (interface number)
    wLength       = 64     (report size, zero-padded frame)

The useful frame therefore starts *inside* the report, with magic 0x5A, and
the report is padded with zeros up to 64 bytes (:func:`pad_report`):

    Scout ON    : 5a 26 05 07 02 00 01 00  + 56 zeros
    Scout OFF   : 5a 26 05 07 02 00 00 00  + 56 zeros
    Direct ON   : 5a 39 03 00 05 01        + 58 zeros
    Direct OFF  : 5a 39 03 00 05 00        + 58 zeros

On the Python side, ``hid_write()`` consumes the **first byte as the report
ID**: so we write ``b"\\x00" + pad_report(frame)`` (65 bytes) to get
``wValue = 0x0200`` and ``wLength = 64``.

The three possible hidapi paths
----------------------------------
+----------------+-------------------------------------------------+---------------+
| Backend        | What ``hid_write(b"\\x00" + 64 B)`` does          | ``usage_page``|
+================+=================================================+===============+
| macOS / IOKit  | ``IOHIDDeviceSetReport(Output, id=0, 64 B)``     | populated     |
+----------------+-------------------------------------------------+---------------+
| Linux / hidraw | ``write(/dev/hidrawN)``, then automatic fallback | populated     |
|                | to ``HID_REQ_SET_REPORT`` for lack of an OUT EP  | (sysfs)       |
+----------------+-------------------------------------------------+---------------+
| Linux / libusb | detaches ``usbhid``, no OUT EP -> direct control | **absent**    |
|                | transfer ``SET_REPORT``                          | (always 0)    |
+----------------+-------------------------------------------------+---------------+

Practical consequence: with the libusb backend, control-interface selection
can't rely on ``usage_page`` (see ``driver._select_control_interface``).

Card -> host direction
------------------
64-byte notifications on interrupt IN endpoint 0x85:

    5a 02 0a 26 00 07 02 00 01 00 ...   -> ACK of command 0x26, status 0x00
    5a 02 0a 39 00 05 00 ...            -> ACK of command 0x39, status 0x00
    5a 39 05 01 00 40 00 00 ...         -> Direct Mode state response
    5a 1a ...                           -> "a setting changed" notification
    5a 11 0e 02 00 96 00 <f32> ...      -> parameter dump
    5a 09 ... "1.2.250819.0903"         -> info / firmware response

USB reset after toggling Direct Mode
------------------------------------
Direct Mode reconfigures the audio chain: the card **re-enumerates**. The
pcap timeline, starting from the emission of the 0x39 command:

    +0.0002 s : ACK 5a 02 0a 39 00 ...
    +0.005  s : 0x1a notifications then 0x11 dumps
    +0.6    s : USB reset / disconnect -> the old HID handle is dead
    +1.3    s : the device reappears (new /dev/hidrawN, new path)

Any write on the old handle after +0.6 s fails. The driver must therefore
close, wait, then re-enumerate and reopen (``driver.reconnect``).

Common framing
--------------
    +------+--------+--------+-----------------+
    | 0x5A | type   | length | payload         |
    +------+--------+--------+-----------------+
       0       1        2       3 .. 3+length

``length`` is the payload size (3-byte header excluded). The 0x80 bit set in
``type`` signals an error (observed when the card receives an invalid
frame: ``5a 11 80 0e ...``).

Payload of a SET u16 command (type 0x26)
------------------------------------------
    +---------+-----------+----------+
    | feature | param u16 | value u16|
    +---------+-----------+----------+
       0x07      0x0002      0/1        (Scout Mode)

Payload of a 0x26 ACK (type 0x02)
------------------------------------
    <cmd echo> <status> <feature> <param u16> <value u16>
    0x26        0x00     0x07      0x0002      0x0001

Payload of a 0x39 ACK (type 0x02) - **different** layout
-----------------------------------------------------------
    <cmd echo> <status> <param> <value>
    0x39        0x00     0x05    0x00        (Direct Mode OFF acknowledged)

Hence the dedicated accessors :attr:`Frame.dm_ack_param` /
:attr:`Frame.dm_ack_value`: decoding this ACK with the 0x26 layout gives a
wrong ``param`` and ``value``.

Payload of a Direct Mode command / response (type 0x39)
--------------------------------------------------------
    write : <feature 0x00> <param 0x05> <value 0/1>
    read  : request  01 20 00 00 00
            response 01 00 40 00 00   -> bit 0x20 of payload[1] = enabled

Payload of a parameter dump (type 0x11)
-------------------------------------------
    <count u16> then ``count`` 6-byte entries:
    <0x96> <param id> <float32 little-endian value>

    e.g. ``96 05 a4 70 3d 3f`` -> param 0x05 = 0.74
         ``96 00 00 00 80 3f`` -> param 0x00 = 1.0

Payload of a SET FLOAT command (type 0x12) - confirmed by the "Sound Mode"
captures
-------------------------------------------------------------------------
    +------+------+----------+-----------------+
    | 0x01 | 0x96 | param id | f32 LE value     |
    +------+------+----------+-----------------+

``0x96`` is the same TLV marker as the one found in parameter-dump (type
0x11) entries: a ``0x12`` write therefore has the same shape as a read
entry, prefixed with ``0x01`` (role not identified - constant across all
observed captures, left as-is).

    param 0x00        : SBX master (0/1)
    param 0x01        : master gain/compensation
    param 0x09        : equalizer on/off (0/1)
    params 0x0b..0x14 : the 10 equalizer bands, in dB
    param 0x0a        : Preamp (input gain, in dB)

``param 0x0a`` was ``0.0`` in all 51 sound-mode captures, which initially
suggested a preset id ("0 = manual"). The ``Equalizer-manual.pcapng``
capture (individual slider variations) shows this same parameter sliding
continuously from ``+6.1`` to ``-8.5``, exactly like an EQ band: it's
actually the **Preamp** slider, simply left at 0 dB by all captured modes.

A Creative application "sound mode" (one ``Equalizer-*.pcapng`` file per
mode in the provided captures) is an ordered sequence of these ``0x12``
writes; the card's ACK is ``5a 02 0a 12 00 ...``
(``Frame.ack_command``/``Frame.ack_status``/``Frame.ack_ok`` suffice, the
ACK layout doesn't follow ``0x26``'s). No USB reset is triggered by these
writes. See :mod:`soundblaster_g8.sound_modes` for the sequences extracted
from the captures and :func:`build_set_float` for the encoding.

CrystalVoice parameters (same 0x12 frame, marker ``TLV_CRYSTALVOICE``)
----------------------------------------------------------------------
CrystalVoice reuses the same numeric param ids as the equalizer, which is
exactly why the marker (0x95 instead of 0x96) has to be part of the key -
see :class:`DecodedState`. From the ``CrystalVoice-*.pcapng`` captures:

    param 0x00        : Acoustic Echo Cancellation (0/1)
    param 0x04        : Noise Reduction (0/1)
    param 0x05        : Noise Reduction level, 0.0-1.0
    param 0x0a        : Voice Morph on/off (0/1)
    params 0x0b..0x12 : the 8 Voice Morph parameters (one preset)
    param 0x13        : Microphone Equalizer on/off (0/1)
    params 0x14..0x1d : the 10 Microphone Equalizer bands, in dB
    param 0x2c        : Smart Volume (0/1)

Like a sound mode, a Voice Morph / Microphone Equalizer preset is just an
ordered sequence of these writes - the enable bit (0x0a / 0x13) is
**never** part of it, so a preset applied while the feature is off is
ACK'd but inaudible. See :mod:`soundblaster_g8.crystalvoice_presets`.

Decoder parameters (same 0x12 frame, marker ``TLV_DECODER``)
------------------------------------------------------------
The Dolby Digital decoder's Dynamic Range Control is a third namespace on
the same frame, with marker 0x97. From ``Decodeur.pcapng`` (one write per
click, each ACK'd by ``5a 02 0a 12 00`` then echoed in a 0x11 dump):

    param 0x02        : DRC mode, 1.0 = Normal, 3.0 = Full, 2.0 = Night

The values aren't contiguous with the display order (Normal, Full, Night):
they were read from the capture, not inferred. As for Scout Mode and Sound
Mode, no read frame for the active mode was observed.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Optional

# --- Framing constants ---------------------------------------------------

MAGIC = 0x5A  # 1st byte of every frame
HEADER_SIZE = 3  # magic + type + length
ERROR_FLAG = 0x80  # bit set in the "type" field on error

#: Size of a HID report on the control interface (both in and out).
REPORT_SIZE = 64

#: Report ID used in ``wValue``: 0x00 -> wValue = 0x0200.
REPORT_ID = 0x00

#: Legacy report ID (wValue = 0x025A), kept for the fallback retry.
LEGACY_REPORT_ID = 0x5A

# Host -> card frame types
CMD_SET = 0x26  # write a u16 parameter
CMD_DIRECT_MODE = 0x39  # write / read Direct Mode
CMD_INFO = 0x09  # identity query (firmware) - used as a probe
CMD_SET_FLOAT = 0x12  # write a float32 (documented, unused)

# Card -> host frame types
NOTIF_ACK = 0x02  # command acknowledgment
NOTIF_PARAMS = 0x11  # parameter dump (float TLV)
NOTIF_STATE_CHANGED = 0x1A  # "a setting changed", emitted in a burst after 0x39

# Marker for a TLV entry in a parameter dump
TLV_FLOAT = 0x96

#: Marker for CrystalVoice float parameters (distinct namespace from
#: TLV_FLOAT: EQ/sound-mode and CrystalVoice params reuse the same numeric
#: ids, e.g. param 0x00, so the marker is what disambiguates them - see
#: CrystalVoice-*.pcapng captures).
TLV_CRYSTALVOICE = 0x95

#: Marker for the Dolby Digital decoder's parameters (third namespace, same
#: rationale as TLV_CRYSTALVOICE - see Decodeur.pcapng).
TLV_DECODER = 0x97

# ACK statuses
STATUS_OK = 0x00

# --- Feature identifiers ----------------------------------------
# Scout Mode and Direct Mode are confirmed by the captures. Other features
# (CrystalVoice, equalizer) require a dedicated USB capture before they can
# be added here (see "Not yet implemented").

FEATURE_SCOUT = 0x07
PARAM_SCOUT_ENABLED = 0x0002

#: (feature, param) confirmed by pcap analysis
SCOUT_MODE = (FEATURE_SCOUT, PARAM_SCOUT_ENABLED)

# Direct Mode - identifiers extracted from the USB captures
FEATURE_DIRECT_MODE = 0x00
PARAM_DIRECT_MODE = 0x05

# Sound mode / equalizer - parameter identifiers extracted from the "Sound
# Mode" captures (CMD_SET_FLOAT command, type 0x12).
PARAM_SBX_MASTER = 0x00  # SBX master (0/1)
PARAM_MASTER_GAIN = 0x01  # master gain/compensation
PARAM_EQ_ENABLED = 0x09  # equalizer on/off (0/1)
PARAM_PREAMP = 0x0A  # Preamp (input gain, in dB)
EQ_BAND_PARAMS = tuple(range(0x0B, 0x15))  # the 10 bands, in dB

# CrystalVoice - parameter identifiers extracted from the
# CrystalVoice-*.pcapng captures (CMD_SET_FLOAT, marker TLV_CRYSTALVOICE).
PARAM_CV_ECHO_CANCELLATION = 0x00  # Acoustic Echo Cancellation on/off
PARAM_CV_NOISE_REDUCTION_ENABLED = 0x04  # Noise Reduction on/off
PARAM_CV_NOISE_REDUCTION_LEVEL = 0x05  # Noise Reduction level, 0.0-1.0
PARAM_CV_VOICE_MORPH_ENABLED = 0x0A  # Voice Morph on/off
PARAM_CV_MIC_EQ_ENABLED = 0x13  # Microphone Equalizer on/off
PARAM_CV_SMART_VOICE = 0x2C  # Smart Volume on/off

#: The 8 Voice Morph parameters, written as an ordered block by a preset
#: (see :mod:`soundblaster_g8.crystalvoice_presets`).
CV_VOICE_MORPH_PARAMS = tuple(range(0x0B, 0x13))

#: The 10 Microphone Equalizer bands, in dB (same idea).
CV_MIC_EQ_BAND_PARAMS = tuple(range(0x14, 0x1E))

# Decoder - parameter identifier extracted from Decodeur.pcapng
# (CMD_SET_FLOAT, marker TLV_DECODER).
PARAM_DECODER_MODE = 0x02  # Dynamic Range Control mode (1 / 2 / 3)

#: Constant prefix observed in every SET FLOAT write.
SET_FLOAT_PREFIX = 0x01

#: Payload of the Direct Mode status request (type 0x39).
DIRECT_MODE_STATUS_PAYLOAD = b"\x01\x20\x00\x00\x00"

#: Bit of the status response's 2nd payload byte indicating "Direct Mode active".
DIRECT_MODE_STATUS_BIT = 0x20

#: Payload of the identity probe (``5a 09 01 02``).
INFO_PROBE_PAYLOAD = b"\x02"


# --- Decoding structures --------------------------------------------------


@dataclass(frozen=True)
class ParamEntry:
    """A TLV entry from a parameter dump (type 0x11)."""

    kind: int  # normalement TLV_FLOAT (0x96)
    param_id: int
    raw: bytes  # 4 octets bruts

    @property
    def as_float(self) -> float:
        return struct.unpack("<f", self.raw)[0]

    @property
    def as_int(self) -> int:
        return int.from_bytes(self.raw, "little")

    def __str__(self) -> str:  # pragma: no cover - debug display
        return f"0x{self.param_id:02x}={self.as_float:g} (raw={self.raw.hex()})"


@dataclass(frozen=True)
class Frame:
    """A decoded G8 protocol frame."""

    frame_type: int
    length: int
    payload: bytes
    raw: bytes

    # --- Frame nature ---
    @property
    def is_error(self) -> bool:
        """The 0x80 bit of the type field signals a rejection by the card."""
        return bool(self.frame_type & ERROR_FLAG)

    @property
    def base_type(self) -> int:
        """Frame type without the error bit."""
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

    # --- Decoding an ACK (type 0x02) ---
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
        """Echoed feature - valid for the 0x26 ACK only."""
        return self.payload[2] if len(self.payload) >= 3 else None

    @property
    def ack_param(self) -> Optional[int]:
        """Echoed u16 param - valid for the 0x26 ACK only."""
        if len(self.payload) < 5:
            return None
        return int.from_bytes(self.payload[3:5], "little")

    @property
    def ack_value(self) -> Optional[int]:
        """Echoed 2-byte value - valid for the 0x26 ACK only."""
        if len(self.payload) < 7:
            return None
        return int.from_bytes(self.payload[5:7], "little")

    # --- Decoding a 0x39 command ACK (different layout from 0x26) ---
    @property
    def dm_ack_param(self) -> Optional[int]:
        """Echoed param in a 0x39 ACK: ``5a 02 0a 39 00 [05] 00``."""
        return self.payload[2] if len(self.payload) >= 3 else None

    @property
    def dm_ack_value(self) -> Optional[int]:
        """Echoed value in a 0x39 ACK: ``5a 02 0a 39 00 05 [00]``."""
        return self.payload[3] if len(self.payload) >= 4 else None

    # --- Decoding a Direct Mode status response (type 0x39) ---
    @property
    def direct_mode_enabled(self) -> Optional[bool]:
        """Direct Mode state in a ``5a 39 05 01 <bits> ...`` response."""
        if self.base_type != CMD_DIRECT_MODE or len(self.payload) < 2:
            return None
        return bool(self.payload[1] & DIRECT_MODE_STATUS_BIT)

    # --- Decoding a parameter dump (type 0x11) ---
    @property
    def params(self) -> list[ParamEntry]:
        return parse_params(self.payload) if self.is_params else []

    # --- Decoding an info response (type 0x09) ---
    @property
    def info_text(self) -> Optional[str]:
        """ASCII string contained in a 0x09 response (firmware version)."""
        if self.base_type != CMD_INFO:
            return None
        printable = bytes(b for b in self.payload if 0x20 <= b < 0x7F)
        return printable.decode("ascii", "ignore") or None

    def describe(self) -> str:
        """Human-readable summary, used by the debug tool and logs."""
        flag = " [ERROR]" if self.is_error else ""
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
    """State cache fed by the received notifications."""

    #: Keyed by (TLV marker, param id): EQ/sound-mode params (TLV_FLOAT) and
    #: CrystalVoice params (TLV_CRYSTALVOICE) reuse the same numeric ids, so
    #: the marker must be part of the key to avoid mixing the two features.
    params: dict[tuple[int, int], float] = field(default_factory=dict)
    features: dict[tuple[int, int], int] = field(default_factory=dict)

    def apply(self, frame: Frame) -> None:
        if frame.is_error:
            return
        if frame.is_params:
            for entry in frame.params:
                self.params[(entry.kind, entry.param_id)] = entry.as_float
        elif frame.is_ack and frame.ack_ok:
            if frame.ack_command == CMD_DIRECT_MODE:
                param, value = frame.dm_ack_param, frame.dm_ack_value
                if param is not None and value is not None:
                    self.features[(FEATURE_DIRECT_MODE, param)] = value
                return
            feature, param, value = frame.ack_feature, frame.ack_param, frame.ack_value
            if feature is not None and param is not None and value is not None:
                self.features[(feature, param)] = value


# --- Encoding ----------------------------------------------------------------


def pad_report(frame: bytes, size: int = REPORT_SIZE) -> bytes:
    """Pads a frame with zeros up to the size of a HID report.

    Interface 4 has no OUT endpoint: the write goes out as SET_REPORT with
    ``wLength = 64``, so the frame must be zero-padded like the official
    application does.

    >>> pad_report(b"\\x5a\\x39\\x03\\x00\\x05\\x01")[:6].hex()
    '5a3903000501'
    >>> len(pad_report(b"\\x5a\\x39\\x03\\x00\\x05\\x01"))
    64
    """
    if len(frame) > size:
        raise ValueError(f"frame too long for a {size}-byte report: {len(frame)}")
    return bytes(frame) + bytes(size - len(frame))


def build_frame(frame_type: int, payload: bytes) -> bytes:
    """Builds a ``5a <type> <len> <payload>`` frame (unpadded).

    Padding to 64 bytes and the report-ID prefix are added by the transport
    layer (:meth:`driver.SoundBlasterG8Driver._send_raw`).
    """
    if not 0 <= frame_type <= 0xFF:
        raise ValueError(f"invalid frame type: {frame_type}")
    if len(payload) > 0xFF:
        raise ValueError(f"payload too long: {len(payload)} bytes")
    return bytes([MAGIC, frame_type, len(payload)]) + bytes(payload)


def build_set_u16(feature: int, param: int, value: int) -> bytes:
    """Builds a SET command (type 0x26) with a 16-bit value.

    >>> build_set_u16(FEATURE_SCOUT, PARAM_SCOUT_ENABLED, 1).hex()
    '5a26050702000100'
    """
    payload = bytes([feature]) + param.to_bytes(2, "little") + value.to_bytes(2, "little")
    return build_frame(CMD_SET, payload)


def build_set_bool(feature: int, param: int, enabled: bool) -> bytes:
    """SET command for a boolean (Scout Mode, etc.)."""
    return build_set_u16(feature, param, 1 if enabled else 0)


def build_scout_mode(enabled: bool) -> bytes:
    """Scout Mode on/off frame.

    >>> build_scout_mode(True).hex()
    '5a26050702000100'
    >>> build_scout_mode(False).hex()
    '5a26050702000000'
    """
    return build_set_bool(*SCOUT_MODE, enabled)


def build_direct_mode(enabled: bool) -> bytes:
    """Direct Mode on/off frame (unpadded).

    >>> build_direct_mode(True).hex()
    '5a3903000501'
    >>> build_direct_mode(False).hex()
    '5a3903000500'
    """
    payload = bytes([FEATURE_DIRECT_MODE, PARAM_DIRECT_MODE, 1 if enabled else 0])
    return build_frame(CMD_DIRECT_MODE, payload)


def build_set_float(param: int, value: float, marker: int = TLV_FLOAT) -> bytes:
    """Builds a SET FLOAT command (type 0x12) - sound mode / equalizer.

    >>> build_set_float(PARAM_EQ_ENABLED, 1.0).hex()
    '5a12070196090000803f'
    >>> build_set_float(0x0b, -4.0).hex()
    '5a120701960b000080c0'
    """
    payload = (
        bytes([SET_FLOAT_PREFIX, marker, param]) + struct.pack("<f", value)
    )
    return build_frame(CMD_SET_FLOAT, payload)


def build_set_crystalvoice_float(param: int, value: float) -> bytes:
    """SET FLOAT command for a CrystalVoice parameter (marker TLV_CRYSTALVOICE).

    >>> build_set_crystalvoice_float(PARAM_CV_NOISE_REDUCTION_ENABLED, 1.0).hex()
    '5a12070195040000803f'
    """
    return build_set_float(param, value, marker=TLV_CRYSTALVOICE)


def build_set_decoder_float(param: int, value: float) -> bytes:
    """SET FLOAT command for a decoder parameter (marker TLV_DECODER).

    >>> build_set_decoder_float(PARAM_DECODER_MODE, 1.0).hex()
    '5a12070197020000803f'
    """
    return build_set_float(param, value, marker=TLV_DECODER)


def build_direct_mode_status() -> bytes:
    """Direct Mode status-read frame.

    >>> build_direct_mode_status().hex()
    '5a39050120000000'
    """
    return build_frame(CMD_DIRECT_MODE, DIRECT_MODE_STATUS_PAYLOAD)


def build_info_probe() -> bytes:
    """Identity query frame, used as a probe after a reset.

    >>> build_info_probe().hex()
    '5a090102'
    """
    return build_frame(CMD_INFO, INFO_PROBE_PAYLOAD)


# --- Decoding ----------------------------------------------------------------


def parse_frame(data: bytes) -> Optional[Frame]:
    """Decodes a received frame. Returns None if the buffer isn't usable.

    Received reports are always 64 bytes, zero-padded: the ``length`` field
    is used to isolate the useful payload.
    """
    if not data:
        return None

    buf = bytes(data)

    # Some hidapi backends prefix the report ID (0x00 when reports aren't
    # numbered): resynchronize on the 0x5A magic byte.
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
    """Decodes the payload of a parameter dump (type 0x11)."""
    if len(payload) < 2:
        return []

    count = int.from_bytes(payload[0:2], "little")
    entries: list[ParamEntry] = []
    offset = 2
    # Bounded by the buffer actually available: the announced count isn't
    # always consistent with the report size.
    while len(entries) < count and offset + 6 <= len(payload):
        kind = payload[offset]
        param_id = payload[offset + 1]
        raw = payload[offset + 2:offset + 6]
        entries.append(ParamEntry(kind=kind, param_id=param_id, raw=raw))
        offset += 6
    return entries
