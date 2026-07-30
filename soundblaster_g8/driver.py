"""
Driver HID pour la carte son Creative Sound Blaster G8.

Le protocole (framing, opcodes, identifiants de paramètres) est isolé dans
:mod:`soundblaster_g8.protocol`. Ce module ne s'occupe que des I/O HID.

Points clés de l'implémentation (issus de l'analyse du pcap) :

1. La carte expose deux interfaces HID. Le canal de contrôle est celui de
   *usage page* ``0xFF01`` (interface 4). Ouvrir le device via
   ``hid.device().open(VID, PID)`` peut tomber sur l'interface Consumer
   (usage page 0x0C, interface 3) qui rejette les commandes : on ouvre donc
   explicitement le bon ``path`` retourné par ``hid.enumerate()``.
2. Les commandes partent en transfert de **contrôle** ``SET_REPORT``
   (``wValue=0x025A``), ce que fait ``hid_write()`` dès lors que le premier
   octet du buffer vaut 0x5A. Il ne faut donc *pas* de padding à 64 octets :
   l'application officielle envoie exactement 8 octets.
3. Les réponses arrivent en notifications de 64 octets sur l'endpoint
   interrupt IN 0x85, lues via ``hid_read``.

Compatible macOS et Linux (et Windows via hidapi, non testé).
"""

from __future__ import annotations

import platform
import time
from typing import Optional

try:
    import hid  # type: ignore
except ImportError:  # pragma: no cover - dépendance déclarée dans pyproject
    hid = None  # type: ignore

from . import protocol
from .protocol import DecodedState, Frame

# Plateforme courante : 'Darwin' (macOS), 'Linux', 'Windows'
PLATFORM = platform.system()

# Identifiants USB
VENDOR_ID = 0x041E  # Creative Technology Ltd
PRODUCT_ID = 0x329B  # Sound Blaster G8

# Interface HID de contrôle (voir docstring de protocol.py)
CONTROL_USAGE_PAGE = 0xFF01
CONTROL_INTERFACE_NUMBER = 4

# Taille des rapports d'entrée sur l'interface de contrôle
INPUT_REPORT_SIZE = 64

# Délais par défaut (ms)
ACK_TIMEOUT_MS = 300
DRAIN_TIMEOUT_MS = 5


class SoundBlasterG8Error(Exception):
    """Erreur générique de la carte Sound Blaster G8."""


class DeviceNotFoundError(SoundBlasterG8Error):
    """L'interface HID de contrôle n'a pas été trouvée."""


class DeviceConnectionError(SoundBlasterG8Error):
    """L'ouverture du device HID a échoué (souvent un problème de droits)."""


class CommandRejectedError(SoundBlasterG8Error):
    """La carte a explicitement rejeté la commande envoyée."""


class FeatureNotSupportedError(SoundBlasterG8Error):
    """Fonction non encore reversée : aucune trame USB connue."""


def _log(message: str) -> None:
    print(f"[SoundBlasterG8Driver] {message}")


class SoundBlasterG8Driver:
    """Driver HID de la Sound Blaster G8.

    Le driver peut fonctionner en mode simulation (aucun matériel détecté) :
    dans ce cas les commandes sont journalisées mais rien n'est envoyé, et
    :meth:`is_connected` renvoie ``False``.
    """

    def __init__(self, debug: bool = False, allow_simulation: bool = True):
        self._device = None
        self._device_info: dict = {}
        self._debug = debug
        self._allow_simulation = allow_simulation
        self._simulated = False
        self._state = DecodedState()
        _log(f"Initialisation du driver (plateforme: {PLATFORM})")

    # ------------------------------------------------------------------
    # Découverte et connexion
    # ------------------------------------------------------------------

    @staticmethod
    def list_interfaces() -> list[dict]:
        """Retourne toutes les interfaces HID exposées par la carte."""
        if hid is None:
            return []
        try:
            return list(hid.enumerate(VENDOR_ID, PRODUCT_ID))
        except Exception as exc:  # pragma: no cover - dépend du back-end
            _log(f"Échec de l'énumération HID: {exc}")
            return []

    @classmethod
    def _select_control_interface(cls, interfaces: list[dict]) -> Optional[dict]:
        """Choisit l'interface vendor (usage page 0xFF01 / interface 4).

        L'ordre d'énumération de hidapi n'est pas garanti : on filtre donc
        explicitement au lieu de prendre la première interface trouvée.
        """
        for info in interfaces:
            if info.get("usage_page") == CONTROL_USAGE_PAGE:
                return info
        # Repli : sur certains back-ends usage_page peut être absent (0).
        for info in interfaces:
            if info.get("interface_number") == CONTROL_INTERFACE_NUMBER:
                return info
        return None

    def connect(self) -> bool:
        """Ouvre l'interface HID de contrôle.

        Returns:
            ``True`` si la carte est réellement connectée, ``False`` en mode
            simulation.

        Raises:
            DeviceNotFoundError / DeviceConnectionError si ``allow_simulation``
            est ``False``.
        """
        if self._device is not None:
            _log("Déjà connecté")
            return True

        _log("Tentative de connexion à la carte Sound Blaster G8...")

        if hid is None:
            return self._fail("le module 'hid' (hidapi) n'est pas installé",
                              DeviceConnectionError)

        interfaces = self.list_interfaces()
        _log(f"Recherche du device HID VID={VENDOR_ID:04x}, PID={PRODUCT_ID:04x}...")

        if self._debug:
            for info in interfaces:
                _log(
                    f"  interface={info.get('interface_number')} "
                    f"usage_page=0x{info.get('usage_page', 0):04x} "
                    f"usage=0x{info.get('usage', 0):04x} "
                    f"path={info.get('path')}"
                )

        if not interfaces:
            return self._fail(
                "aucune interface HID trouvée pour la Sound Blaster G8",
                DeviceNotFoundError,
            )

        target = self._select_control_interface(interfaces)
        if target is None:
            return self._fail(
                f"interface de contrôle (usage page 0x{CONTROL_USAGE_PAGE:04x}) "
                f"introuvable parmi {len(interfaces)} interface(s) HID",
                DeviceNotFoundError,
            )

        try:
            device = hid.device()
            device.open_path(target["path"])
        except Exception as exc:
            return self._fail(
                f"ouverture de l'interface de contrôle impossible: {exc}",
                DeviceConnectionError,
            )

        self._device = device
        self._device_info = target
        self._simulated = False

        try:
            device.set_nonblocking(False)
        except Exception:  # pragma: no cover - certains back-ends l'ignorent
            pass

        _log(
            "Connexion HID établie sur l'interface de contrôle "
            f"(interface={target.get('interface_number')}, "
            f"usage_page=0x{target.get('usage_page', 0):04x})"
        )
        if self._debug:
            _log(f"  Fabricant : {target.get('manufacturer_string')}")
            _log(f"  Produit   : {target.get('product_string')}")
            _log(f"  Série     : {target.get('serial_number')}")

        # Les notifications éventuellement en attente renseignent l'état initial.
        self.poll()
        return True

    def _fail(self, reason: str, exc_type: type[SoundBlasterG8Error]) -> bool:
        """Gère un échec de connexion : exception ou repli en simulation."""
        _log(f"ERREUR: {reason}")
        if not self._allow_simulation:
            raise exc_type(reason)

        self._simulated = True
        _log("Mode simulation activé (aucune commande ne sera envoyée)")
        if PLATFORM == "Darwin":
            _log("Sur macOS, vérifiez : 'system_profiler SPUSBDataType | grep -A5 G8'")
        elif PLATFORM == "Linux":
            _log("Sur Linux, vérifiez 'lsusb', l'accès à /dev/hidraw* et la règle udev")
            _log("  (voir udev/99-soundblaster-g8.rules)")
        return False

    def disconnect(self) -> None:
        """Ferme la connexion HID."""
        if self._device is not None:
            try:
                self._device.close()
                _log("Device HID fermé")
            except Exception as exc:
                _log(f"Erreur lors de la fermeture HID: {exc}")
        self._device = None
        self._device_info = {}
        self._simulated = False

    def is_connected(self) -> bool:
        """``True`` uniquement si le matériel réel est ouvert."""
        return self._device is not None

    def is_simulated(self) -> bool:
        """``True`` si le driver tourne sans matériel."""
        return self._simulated

    def get_debug_info(self) -> dict:
        """Informations utiles au diagnostic."""
        return {
            "platform": PLATFORM,
            "vendor_id": f"{VENDOR_ID:04x}",
            "product_id": f"{PRODUCT_ID:04x}",
            "connected": self.is_connected(),
            "simulated": self._simulated,
            "interface_number": self._device_info.get("interface_number"),
            "usage_page": self._device_info.get("usage_page"),
            "product_string": self._device_info.get("product_string"),
            "serial_number": self._device_info.get("serial_number"),
            "known_params": {f"0x{k:02x}": v for k, v in self._state.params.items()},
            "known_features": {
                f"0x{f:02x}/0x{p:04x}": v for (f, p), v in self._state.features.items()
            },
        }

    # ------------------------------------------------------------------
    # Couche transport
    # ------------------------------------------------------------------

    def _read_frame(self, timeout_ms: int) -> Optional[Frame]:
        """Lit une notification et la décode (``None`` si rien n'arrive)."""
        if self._device is None:
            return None
        try:
            data = self._device.read(INPUT_REPORT_SIZE, timeout_ms)
        except Exception as exc:
            _log(f"Erreur de lecture HID: {exc}")
            return None

        if not data:
            return None

        frame = protocol.parse_frame(bytes(data))
        if frame is None:
            if self._debug:
                _log(f"<- rapport non décodable: {bytes(data).hex()}")
            return None

        self._state.apply(frame)
        if self._debug:
            _log(f"<- {frame.describe()}")
        return frame

    def poll(self, timeout_ms: int = DRAIN_TIMEOUT_MS, max_frames: int = 16) -> list[Frame]:
        """Vide la file des notifications et met à jour le cache d'état."""
        frames: list[Frame] = []
        for _ in range(max_frames):
            frame = self._read_frame(timeout_ms)
            if frame is None:
                break
            frames.append(frame)
        return frames

    def send_frame(
        self,
        frame_type: int,
        payload: bytes,
        expect_ack: bool = True,
        timeout_ms: int = ACK_TIMEOUT_MS,
    ) -> Optional[Frame]:
        """Envoie une trame et retourne l'ACK correspondant.

        Args:
            frame_type: type de trame (ex. ``protocol.CMD_SET``).
            payload: contenu de la trame, en-tête exclu.
            expect_ack: attendre et retourner l'accusé de réception.
            timeout_ms: budget d'attente de l'ACK.

        Raises:
            CommandRejectedError: la carte a répondu avec le bit d'erreur ou
                un statut non nul.
        """
        data = protocol.build_frame(frame_type, payload)

        if self._device is None:
            _log(f"[simulation] -> {data.hex()}")
            return None

        # On purge les notifications spontanées pour ne pas les confondre
        # avec l'ACK de la commande qui suit.
        self.poll()

        _log(f"-> {data.hex()} (SET_REPORT wValue=0x02{protocol.MAGIC:02x}, {len(data)} octets)")
        try:
            written = self._device.write(data)
        except Exception as exc:
            raise DeviceConnectionError(f"écriture HID impossible: {exc}") from exc

        if written != len(data) and self._debug:
            _log(f"AVERTISSEMENT: {written} octet(s) écrit(s) sur {len(data)}")

        if not expect_ack:
            return None

        deadline = time.monotonic() + timeout_ms / 1000.0
        while True:
            remaining_ms = int((deadline - time.monotonic()) * 1000)
            if remaining_ms <= 0:
                _log("Aucun ACK reçu (timeout)")
                return None

            frame = self._read_frame(min(remaining_ms, 50))
            if frame is None:
                continue

            if frame.is_error:
                raise CommandRejectedError(
                    f"commande rejetée par la carte: {frame.describe()}"
                )
            if frame.is_ack and frame.ack_command == frame_type:
                if not frame.ack_ok:
                    raise CommandRejectedError(
                        f"statut d'erreur {frame.ack_status}: {frame.describe()}"
                    )
                return frame
            # Les dumps de paramètres (0x11) arrivent aussi : ils alimentent le
            # cache d'état (déjà fait dans _read_frame) et on continue d'attendre.

    # ------------------------------------------------------------------
    # Fonctions génériques
    # ------------------------------------------------------------------

    def set_feature_u16(self, feature: int, param: int, value: int) -> bool:
        """Écrit un paramètre 16 bits et vérifie l'écho de l'ACK."""
        if self._device is None:
            _log(
                f"[simulation] feature=0x{feature:02x} param=0x{param:04x} value={value}"
            )
            return False

        payload = (
            bytes([feature])
            + param.to_bytes(2, "little")
            + value.to_bytes(2, "little")
        )
        ack = self.send_frame(protocol.CMD_SET, payload)
        if ack is None:
            return False

        if ack.ack_feature != feature or ack.ack_param != param:
            _log(
                "AVERTISSEMENT: l'ACK ne correspond pas à la commande "
                f"(attendu 0x{feature:02x}/0x{param:04x}, "
                f"reçu {ack.describe()})"
            )
            return False

        if ack.ack_value is not None and ack.ack_value != value:
            _log(
                f"AVERTISSEMENT: valeur appliquée {ack.ack_value} "
                f"au lieu de {value}"
            )
            return False

        return True

    def set_feature_bool(self, feature: int, param: int, enabled: bool) -> bool:
        return self.set_feature_u16(feature, param, 1 if enabled else 0)

    def get_feature_cached(self, feature: int, param: int) -> Optional[int]:
        """Dernière valeur connue d'un paramètre (via les ACK reçus)."""
        self.poll()
        return self._state.features.get((feature, param))

    # ------------------------------------------------------------------
    # Scout Mode (confirmé par la capture USB)
    # ------------------------------------------------------------------

    def set_scout_mode(self, enabled: bool) -> bool:
        """Active/désactive le Scout Mode.

        Trame envoyée : ``5a 26 05 07 02 00 01 00`` (ON) /
        ``5a 26 05 07 02 00 00 00`` (OFF).

        Returns:
            ``True`` si la carte a acquitté la commande.
        """
        action = "activation" if enabled else "désactivation"
        _log(f"Scout Mode : {action}")
        try:
            ok = self.set_feature_bool(*protocol.SCOUT_MODE, enabled)
        except SoundBlasterG8Error as exc:
            _log(f"ERREUR Scout Mode: {exc}")
            return False

        if ok:
            _log(f"Scout Mode {'activé' if enabled else 'désactivé'} (confirmé par la carte)")
        elif self._device is not None:
            _log("Scout Mode : la carte n'a pas confirmé la commande")
        return ok

    def get_scout_mode(self) -> Optional[bool]:
        """État du Scout Mode d'après le dernier ACK reçu.

        La commande de lecture n'a pas encore été identifiée dans le pcap :
        on se base sur l'écho des commandes déjà envoyées. Retourne ``None``
        si l'état est inconnu.
        """
        value = self.get_feature_cached(*protocol.SCOUT_MODE)
        return None if value is None else bool(value)

    # ------------------------------------------------------------------
    # Fonctions non encore reversées
    # ------------------------------------------------------------------

    def _unsupported(self, name: str) -> bool:
        _log(
            f"'{name}' n'est pas encore implémenté : la trame USB correspondante "
            "n'a pas été capturée. Utilisez 'python tools/g8_probe.py --monitor' "
            "pendant que l'application Creative modifie ce réglage."
        )
        return False

    def set_direct_mode(self, enabled: bool) -> bool:
        return self._unsupported("Direct Mode")

    def get_direct_mode(self) -> Optional[bool]:
        return None

    def set_crystalvoice(self, enabled: bool) -> bool:
        return self._unsupported("CrystalVoice")

    def get_crystalvoice(self) -> Optional[bool]:
        return None

    def eq_set_band(self, index: int, value: float) -> bool:
        if not 0 <= index < 10:
            raise ValueError(f"index de bande hors limites: {index}")
        return self._unsupported(f"Égaliseur (bande {index})")

    def eq_get_all_bands(self) -> Optional[list[float]]:
        return None

    def eq_load_preset(self, preset_name: str) -> bool:
        return self._unsupported(f"Preset EQ '{preset_name}'")

    def eq_save_preset(self, preset_name: str) -> bool:
        return self._unsupported(f"Sauvegarde du preset EQ '{preset_name}'")

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "SoundBlasterG8Driver":
        self.connect()
        return self

    def __exit__(self, *_exc) -> None:
        self.disconnect()


# Instance singleton
_driver_instance: Optional[SoundBlasterG8Driver] = None


def get_driver(debug: bool = False) -> SoundBlasterG8Driver:
    """Retourne l'instance singleton du driver."""
    global _driver_instance
    if _driver_instance is None:
        _driver_instance = SoundBlasterG8Driver(debug=debug)
    return _driver_instance
