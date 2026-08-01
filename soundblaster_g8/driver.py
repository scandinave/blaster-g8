"""
Driver HID pour la carte son Creative Sound Blaster G8.

Le protocole (framing, opcodes, identifiants de paramètres) est isolé dans
:mod:`soundblaster_g8.protocol`, la sélection du backend hidapi dans
:mod:`soundblaster_g8.hidbackend`. Ce module ne s'occupe que des I/O HID.

Points clés de l'implémentation (issus de l'analyse du pcap) :

1. La carte expose deux interfaces HID. Le canal de contrôle est celui de
   *usage page* ``0xFF01`` (interface 4). Ouvrir le device via
   ``hid.device().open(VID, PID)`` peut tomber sur l'interface Consumer
   (usage page 0x0C, interface 3) qui rejette les commandes : on ouvre donc
   explicitement le bon ``path`` retourné par ``enumerate()``.
2. L'interface 4 n'a **pas d'endpoint interrupt OUT** : toute écriture est un
   transfert de contrôle ``SET_REPORT`` ``wValue=0x0200`` / ``wLength=64``.
   On écrit donc systématiquement ``b"\\x00" + pad_report(frame)``.
3. Les réponses arrivent en notifications de 64 octets sur l'endpoint
   interrupt IN 0x85, lues via ``hid_read``.
4. Une bascule du Direct Mode (cmd 0x39) provoque un **reset USB** ~0.6 s
   après l'ACK : le handle doit être fermé puis réouvert (:meth:`reconnect`).
5. Les handles hidapi ne sont pas *thread-safe* et la GUI appelle le driver
   depuis un worker thread : toutes les I/O sont sérialisées par un verrou.

Compatible macOS et Linux (et Windows via hidapi, non testé).
"""

from __future__ import annotations

import platform
import threading
import time
from typing import Callable, Optional

from . import hidbackend, protocol
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
INPUT_REPORT_SIZE = protocol.REPORT_SIZE

# Délais par défaut (ms)
ACK_TIMEOUT_MS = 300
DRAIN_TIMEOUT_MS = 5
PROBE_TIMEOUT_MS = 400

# Reconnexion après le reset USB provoqué par une bascule du Direct Mode.
# Chronologie du pcap : reset à +0.6 s, réapparition du device à +1.3 s.
RECONNECT_TIMEOUT_S = 12.0
RECONNECT_INTERVAL_S = 0.25
RECONNECT_GRACE_S = 1.0

# Durée pendant laquelle on absorbe les notifications 0x1a / 0x11 émises en
# rafale juste après une bascule du Direct Mode.
TOGGLE_DRAIN_S = 0.25


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
        self._serial_number: Optional[str] = None
        self._debug = debug
        self._allow_simulation = allow_simulation
        self._simulated = False
        self._state = DecodedState()

        # Les handles hidapi ne sont pas thread-safe : toutes les I/O (write,
        # read, open, close) passent par ce verrou. RLock car set_direct_mode()
        # appelle reconnect() en gardant déjà le verrou.
        self._io_lock = threading.RLock()
        self._in_reconnect = False

        #: Callback optionnel ``(bool) -> None`` appelé au début et à la fin
        #: d'une reconnexion, pour que la GUI puisse prévenir l'utilisateur.
        self.on_reconnecting: Optional[Callable[[bool], None]] = None

        _log(f"Initialisation du driver (plateforme: {PLATFORM}, "
             f"backend HID: {hidbackend.backend_name()})")

    # ------------------------------------------------------------------
    # Découverte et connexion
    # ------------------------------------------------------------------

    @staticmethod
    def backend_name() -> str:
        """Nom du backend hidapi retenu (``hidraw``, ``libusb``, ``iokit``...)."""
        return hidbackend.backend_name()

    @staticmethod
    def list_interfaces() -> list[dict]:
        """Retourne toutes les interfaces HID exposées par la carte."""
        try:
            return hidbackend.enumerate(VENDOR_ID, PRODUCT_ID)
        except ImportError as exc:
            _log(f"Backend HID indisponible: {exc}")
            return []
        except Exception as exc:  # pragma: no cover - dépend du back-end
            _log(f"Échec de l'énumération HID: {exc}")
            return []

    @classmethod
    def _select_control_interface(
        cls,
        interfaces: list[dict],
        serial_number: Optional[str] = None,
    ) -> Optional[dict]:
        """Choisit l'interface vendor (usage page 0xFF01 / interface 4).

        L'ordre d'énumération de hidapi n'est pas garanti : on filtre donc
        explicitement au lieu de prendre la première interface trouvée. Trois
        critères, du plus fiable au plus permissif :

        1. ``usage_page == 0xFF01`` : chemin normal sur macOS/IOKit et
           Linux/hidraw.
        2. ``interface_number == 4`` : **chemin normal sur Linux avec le
           backend libusb**, qui ne renseigne jamais ``usage_page`` (il vaut
           toujours 0 dans ``hid_enumerate``). Ce n'est donc pas un cas
           dégradé mais la voie habituelle des wheels ``pip install hidapi``.
        3. ``input_report_length == 64`` : dernier recours, l'interface
           Consumer utilisant des rapports de 16 octets.
        """
        candidates = interfaces
        # Plusieurs cartes branchées : on reste sur celle déjà ouverte.
        if serial_number:
            same_card = [i for i in interfaces if i.get("serial_number") == serial_number]
            if same_card:
                candidates = same_card

        for info in candidates:
            if info.get("usage_page") == CONTROL_USAGE_PAGE:
                return info
        for info in candidates:
            if info.get("interface_number") == CONTROL_INTERFACE_NUMBER:
                return info
        for info in candidates:
            if info.get("input_report_length") == INPUT_REPORT_SIZE:
                return info
        return None

    def connect(self, force: bool = False) -> bool:
        """Ouvre l'interface HID de contrôle.

        Args:
            force: rouvre le device même si un handle est déjà mémorisé. Sert
                après un reset USB, où l'ancien handle est encore non nul mais
                pointe sur un nœud moribond.

        Returns:
            ``True`` si la carte est réellement connectée, ``False`` en mode
            simulation.

        Raises:
            DeviceNotFoundError / DeviceConnectionError si ``allow_simulation``
            est ``False``.
        """
        with self._io_lock:
            if self._device is not None:
                if not force:
                    _log("Déjà connecté")
                    return True
                self._close_quietly()

            _log("Tentative de connexion à la carte Sound Blaster G8...")

            if not hidbackend.is_available():
                return self._fail(
                    "aucun backend hidapi disponible ('pip install hidapi')",
                    DeviceConnectionError,
                )

            interfaces = self.list_interfaces()
            _log(
                f"Recherche du device HID VID={VENDOR_ID:04x}, PID={PRODUCT_ID:04x} "
                f"(backend {hidbackend.backend_name()})..."
            )

            if self._debug:
                for info in interfaces:
                    _log(
                        f"  interface={info.get('interface_number')} "
                        f"usage_page=0x{info.get('usage_page', 0):04x} "
                        f"usage=0x{info.get('usage', 0):04x} "
                        f"in_len={info.get('input_report_length')} "
                        f"path={info.get('path')}"
                    )

            if not interfaces:
                return self._fail(
                    "aucune interface HID trouvée pour la Sound Blaster G8",
                    DeviceNotFoundError,
                )

            target = self._select_control_interface(interfaces, self._serial_number)
            if target is None:
                return self._fail(
                    f"interface de contrôle (usage page 0x{CONTROL_USAGE_PAGE:04x} "
                    f"ou interface {CONTROL_INTERFACE_NUMBER}) introuvable parmi "
                    f"{len(interfaces)} interface(s) HID",
                    DeviceNotFoundError,
                )

            try:
                device = hidbackend.open_path(target["path"])
            except Exception as exc:
                return self._fail(
                    f"ouverture de l'interface de contrôle impossible: {exc}",
                    DeviceConnectionError,
                )

            self._device = device
            self._device_info = target
            self._simulated = False
            # Mémorisé au premier connect : après un reset USB, le path change
            # mais le numéro de série permet de rouvrir la même carte.
            if not self._serial_number:
                self._serial_number = target.get("serial_number") or None

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

    def _close_quietly(self) -> None:
        """Ferme le handle courant en ignorant toute erreur (best effort)."""
        device, self._device = self._device, None
        if device is None:
            return
        try:
            device.close()
        except Exception as exc:
            if self._debug:
                _log(f"fermeture du handle ignorée: {exc}")

    def _invalidate_device(self, reason: str) -> None:
        """Marque le handle comme mort (après un reset USB, par exemple)."""
        _log(f"Handle HID invalidé : {reason}")
        self._close_quietly()
        self._device_info = {}

    def disconnect(self) -> None:
        """Ferme la connexion HID."""
        with self._io_lock:
            if self._device is not None:
                self._close_quietly()
                _log("Device HID fermé")
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
            "hid_backend": hidbackend.backend_name(),
            "usage_page_available": hidbackend.provides_usage_page(),
            "vendor_id": f"{VENDOR_ID:04x}",
            "product_id": f"{PRODUCT_ID:04x}",
            "connected": self.is_connected(),
            "simulated": self._simulated,
            "interface_number": self._device_info.get("interface_number"),
            "usage_page": self._device_info.get("usage_page"),
            "product_string": self._device_info.get("product_string"),
            "serial_number": self._device_info.get("serial_number") or self._serial_number,
            "known_params": {f"0x{k:02x}": v for k, v in self._state.params.items()},
            "known_features": {
                f"0x{f:02x}/0x{p:04x}": v for (f, p), v in self._state.features.items()
            },
        }

    # ------------------------------------------------------------------
    # Reconnexion après reset USB
    # ------------------------------------------------------------------

    def reconnect(
        self,
        timeout_s: float = RECONNECT_TIMEOUT_S,
        interval_s: float = RECONNECT_INTERVAL_S,
    ) -> bool:
        """Rouvre le canal de contrôle après un reset USB de la carte.

        Chronologie observée dans le pcap, à partir de la commande 0x39 :
        reset/disconnect à +0.6 s, réapparition du device à +1.3 s. On laisse
        donc une seconde de grâce avant de commencer à réénumérer, puis on
        retente jusqu'au *deadline* : sous Linux, ``udev`` peut n'avoir pas
        encore appliqué les droits sur le nouveau ``/dev/hidrawN`` (course
        classique -> ``PermissionError`` transitoire, à retenter).

        Returns:
            ``True`` si un handle a été rouvert *et* validé par une sonde
            (aller-retour réel avec la carte).
        """
        with self._io_lock:
            if self._in_reconnect:
                return self._device is not None

            self._in_reconnect = True
            self._notify_reconnecting(True)
            try:
                # 1. l'ancien handle est mort : on le ferme sans se soucier des
                #    erreurs (le nœud a pu disparaître entre-temps).
                self._close_quietly()
                self._device_info = {}

                # 2. délai de grâce : inutile d'énumérer avant que la carte ne
                #    soit réapparue.
                time.sleep(RECONNECT_GRACE_S)

                deadline = time.monotonic() + timeout_s
                attempt = 0
                last_error = "aucune interface trouvée"

                while time.monotonic() < deadline:
                    attempt += 1
                    try:
                        interfaces = hidbackend.enumerate(VENDOR_ID, PRODUCT_ID)
                        target = self._select_control_interface(
                            interfaces, self._serial_number
                        )
                        if target is None:
                            last_error = (
                                f"interface de contrôle absente "
                                f"({len(interfaces)} interface(s) énumérée(s))"
                            )
                            raise LookupError(last_error)

                        device = hidbackend.open_path(target["path"])
                    except (OSError, PermissionError, LookupError) as exc:
                        # Retryable : device pas encore réapparu, ou udev n'a
                        # pas fini d'appliquer les droits sur le nouveau nœud.
                        last_error = str(exc) or exc.__class__.__name__
                        if self._debug:
                            _log(f"reconnexion, tentative {attempt} : {last_error}")
                        time.sleep(interval_s)
                        continue
                    except Exception as exc:  # pragma: no cover - back-end exotique
                        last_error = str(exc) or exc.__class__.__name__
                        if self._debug:
                            _log(f"reconnexion, tentative {attempt} : {last_error}")
                        time.sleep(interval_s)
                        continue

                    self._device = device
                    self._device_info = target
                    self._simulated = False
                    try:
                        device.set_nonblocking(False)
                    except Exception:  # pragma: no cover
                        pass

                    # 4. valider par un aller-retour réel : un handle ouvert sur
                    #    un nœud moribond accepte parfois l'open mais rien d'autre.
                    if self._probe():
                        _log(
                            f"Reconnexion réussie après {attempt} tentative(s) "
                            f"(interface={target.get('interface_number')})"
                        )
                        self.poll()
                        return True

                    last_error = "la sonde 0x09 n'a pas répondu"
                    self._close_quietly()
                    time.sleep(interval_s)

                _log(f"ÉCHEC de la reconnexion après {timeout_s:.0f}s : {last_error}")
                return False
            finally:
                self._in_reconnect = False
                self._notify_reconnecting(False)

    def _notify_reconnecting(self, active: bool) -> None:
        callback = self.on_reconnecting
        if callback is None:
            return
        try:
            callback(active)
        except Exception as exc:  # pragma: no cover - dépend de l'appelant
            _log(f"Erreur dans le callback on_reconnecting: {exc}")

    def _probe(self) -> bool:
        """Aller-retour réel avec la carte : ``5a 09 01 02`` -> réponse 0x09.

        La réponse contient la chaîne de version du firmware
        (``1.2.250819.0903`` sur la carte de référence, confirmé par le pcap).
        Sert à s'assurer qu'on n'a pas rouvert le nœud moribond laissé par le
        reset USB : celui-ci accepte l'``open`` mais ne répond plus.
        """
        try:
            frame = self._send_raw(
                protocol.build_info_probe(),
                expect="same_type",
                timeout_ms=PROBE_TIMEOUT_MS,
                allow_legacy_retry=False,
                recover=False,
            )
        except SoundBlasterG8Error as exc:
            if self._debug:
                _log(f"sonde en échec: {exc}")
            return False

        if frame is None:
            return False
        if self._debug:
            _log(f"sonde OK, firmware={frame.info_text!r}")
        return True

    # ------------------------------------------------------------------
    # Couche transport
    # ------------------------------------------------------------------

    def _read_frame(self, timeout_ms: int, recover: bool = True) -> Optional[Frame]:
        """Lit une notification et la décode (``None`` si rien n'arrive)."""
        with self._io_lock:
            device = self._device
            if device is None:
                return None
            try:
                data = device.read(INPUT_REPORT_SIZE, timeout_ms)
            except OSError as exc:
                # Handle mort (reset USB, câble débranché) : on le jette et on
                # tente une reconnexion.
                self._invalidate_device(f"lecture HID impossible: {exc}")
                if recover:
                    self.reconnect()
                return None
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

    def poll(
        self,
        timeout_ms: int = DRAIN_TIMEOUT_MS,
        max_frames: int = 16,
        recover: bool = False,
    ) -> list[Frame]:
        """Vide la file des notifications et met à jour le cache d'état.

        Args:
            recover: tenter une reconnexion si le handle s'avère mort. Faux par
                défaut : après une bascule du Direct Mode la disparition du
                device est attendue et gérée par l'appelant.
        """
        frames: list[Frame] = []
        for _ in range(max_frames):
            frame = self._read_frame(timeout_ms, recover=recover)
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
        return self._send_raw(
            data,
            expect="ack" if expect_ack else None,
            timeout_ms=timeout_ms,
        )

    def _write(self, buf: bytes, recover: bool = True) -> bool:
        """Écriture HID brute, verrouillée, avec détection de handle mort."""
        with self._io_lock:
            device = self._device
            if device is None:
                return False
            _log(f"-> {buf.hex()} ({len(buf)} octets)")
            try:
                written = device.write(buf)
            except OSError as exc:
                self._invalidate_device(f"écriture HID impossible: {exc}")
                if recover:
                    self.reconnect()
                return False
            except Exception as exc:
                raise DeviceConnectionError(f"écriture HID impossible: {exc}") from exc

        if written != len(buf) and self._debug:
            _log(f"AVERTISSEMENT: {written} octet(s) écrit(s) sur {len(buf)}")
        return True

    def _wait_for(
        self,
        expect: str,
        frame_type: int,
        timeout_ms: int,
        recover: bool,
    ) -> Optional[Frame]:
        """Attend la réponse attendue, en ignorant les notifications parasites.

        ``expect="ack"``       : trame de type 0x02 dont ``ack_command`` vaut
        ``frame_type`` (écritures).
        ``expect="same_type"`` : trame du même type que la requête (lectures :
        0x39 -> 0x39, 0x09 -> 0x09, 0x11 -> 0x11).
        """
        deadline = time.monotonic() + timeout_ms / 1000.0
        while True:
            remaining_ms = int((deadline - time.monotonic()) * 1000)
            if remaining_ms <= 0:
                return None

            frame = self._read_frame(min(remaining_ms, 50), recover=recover)
            if frame is None:
                if self._device is None:
                    return None
                continue

            if frame.is_error and frame.base_type in (protocol.NOTIF_ACK, frame_type):
                raise CommandRejectedError(
                    f"commande rejetée par la carte: {frame.describe()}"
                )

            if expect == "ack":
                if frame.is_ack and frame.ack_command == frame_type:
                    if not frame.ack_ok:
                        raise CommandRejectedError(
                            f"statut d'erreur {frame.ack_status}: {frame.describe()}"
                        )
                    return frame
            elif expect == "same_type":
                if frame.base_type == frame_type:
                    return frame

    def _send_raw(
        self,
        frame: bytes,
        expect: Optional[str] = "ack",
        timeout_ms: int = ACK_TIMEOUT_MS,
        allow_legacy_retry: bool = True,
        recover: bool = True,
    ) -> Optional[Frame]:
        """Envoie une trame et attend éventuellement la réponse associée.

        Transport unique (voir ``protocol``) : ``b"\\x00" + pad_report(frame)``,
        soit ``SET_REPORT wValue=0x0200 wLength=64``. Le premier octet est
        consommé par hidapi comme report ID.

        Args:
            frame: trame ``5a <type> <len> <payload>`` non paddée.
            expect: ``"ack"`` (réponse de type 0x02), ``"same_type"`` (réponse
                du même type que la requête) ou ``None`` (fire-and-forget).
            allow_legacy_retry: en cas de time-out, retenter **une seule fois**
                avec l'ancienne forme (trame nue de 8 octets, report ID 0x5A,
                ``wValue=0x025A``). Garde-fou au cas où la carte se révélerait
                plus stricte sur le Scout Mode que ce que montre la capture.
        """
        if not frame or frame[0] != protocol.MAGIC:
            raise ValueError(f"trame invalide (magic attendu 0x5a): {bytes(frame).hex()}")
        frame_type = frame[1]

        with self._io_lock:
            if self._device is None:
                _log(f"[simulation] -> {bytes(frame).hex()}")
                return None

            # Purge : les notifications en attente fausseraient l'appariement.
            # Si le handle est mort (reset USB non annoncé), la purge déclenche
            # la reconnexion et l'écriture partira sur le nouveau handle.
            self.poll(recover=recover)
            if self._device is None:
                _log("Envoi impossible : plus de handle HID valide")
                return None

            report = bytes([protocol.REPORT_ID]) + protocol.pad_report(frame)
            if not self._write(report, recover=recover):
                return None

            if expect is None:
                return None

            response = self._wait_for(expect, frame_type, timeout_ms, recover)
            if response is not None:
                return response

            if not allow_legacy_retry:
                _log("Aucune réponse reçue (timeout)")
                return None

            # Repli historique : trame nue, hidapi prend 0x5A comme report ID
            # -> wValue=0x025A. Un seul essai, journalisé explicitement.
            _log(
                "Aucune réponse à la forme paddée 64 o (wValue=0x0200) : "
                "un unique retry avec l'ancienne forme "
                f"({len(frame)} o, report ID 0x{protocol.LEGACY_REPORT_ID:02x}, "
                "wValue=0x025a)"
            )
            if not self._write(bytes(frame), recover=recover):
                return None

            response = self._wait_for(expect, frame_type, timeout_ms, recover)
            if response is None:
                _log("Aucune réponse reçue (timeout, y compris après le retry)")
            else:
                _log(
                    "ATTENTION: la carte n'accepte que l'ancienne forme "
                    "(report ID 0x5a) - signalez-le, le transport unifié est "
                    "censé fonctionner d'après la capture USB"
                )
            return response

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
        ``5a 26 05 07 02 00 00 00`` (OFF), zéro-paddée à 64 octets.

        Returns:
            ``True`` si la carte a acquitté la commande.
        """
        action = "activation" if enabled else "désactivation"
        _log(f"Scout Mode : {action}")
        with self._io_lock:
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
    # Direct Mode (confirmé par la capture USB)
    # ------------------------------------------------------------------

    def set_direct_mode(self, enabled: bool) -> bool:
        """Active/désactive le Direct Mode.

        Séquence complète (voir la chronologie dans ``protocol``) :

        1. purge des notifications en attente ;
        2. envoi de ``5a 39 03 00 05 <0|1>`` paddé à 64 octets ;
        3. attente de l'ACK ``5a 02 0a 39 00 05 <0|1>`` (il arrive en ~0.2 ms,
           budget 300 ms) avec vérification de l'écho param/valeur ;
        4. drainage des notifications 0x1a et des dumps 0x11 qui suivent ;
        5. la carte se réénumère (reset USB à +0.6 s) : :meth:`reconnect`.

        Returns:
            ``True`` seulement si l'ACK est correct **et** la reconnexion
            validée par une sonde.
        """
        action = "activation" if enabled else "désactivation"
        _log(f"Direct Mode : {action}")

        with self._io_lock:
            if self._device is None:
                _log(f"[simulation] -> {protocol.build_direct_mode(enabled).hex()}")
                return False

            try:
                ack = self._send_raw(
                    protocol.build_direct_mode(enabled),
                    expect="ack",
                    timeout_ms=ACK_TIMEOUT_MS,
                )
            except SoundBlasterG8Error as exc:
                _log(f"ERREUR Direct Mode: {exc}")
                return False

            if ack is None:
                _log("Direct Mode : aucun ACK de la commande 0x39 (timeout)")
                return False

            # L'ACK de 0x39 n'a pas le même layout que celui de 0x26.
            expected = 1 if enabled else 0
            if ack.dm_ack_param != protocol.PARAM_DIRECT_MODE:
                _log(
                    "AVERTISSEMENT: l'ACK 0x39 ne référence pas le param "
                    f"0x{protocol.PARAM_DIRECT_MODE:02x} ({ack.describe()})"
                )
                return False
            if ack.dm_ack_value != expected:
                _log(
                    f"AVERTISSEMENT: valeur appliquée {ack.dm_ack_value} "
                    f"au lieu de {expected} ({ack.describe()})"
                )
                return False

            _log("Direct Mode : commande acquittée, drainage des notifications...")
            self._drain_toggle_notifications()

            _log("Direct Mode : la carte se réénumère, reconnexion...")
            if not self.reconnect():
                _log(
                    "Direct Mode : commande acceptée mais la carte n'a pas pu "
                    "être rouverte après le reset USB"
                )
                return False

            _log(f"Direct Mode {'activé' if enabled else 'désactivé'} (confirmé)")
            return True

    def _drain_toggle_notifications(self) -> None:
        """Absorbe les 0x1a / 0x11 émis en rafale après une bascule du 0x39."""
        deadline = time.monotonic() + TOGGLE_DRAIN_S
        while time.monotonic() < deadline:
            frames = self.poll(timeout_ms=20, max_frames=8)
            if not frames:
                break

    def get_direct_mode(self) -> Optional[bool]:
        """Interroge la carte sur l'état du Direct Mode.

        Requête ``5a 39 05 01 20 00 00 00`` -> réponse de type 0x39
        ``5a 39 05 01 <bits> 40 00 00`` ; le bit 0x20 du 2e octet de payload
        indique que le Direct Mode est actif.

        Returns:
            ``None`` si la carte n'est pas connectée ou ne répond pas.
        """
        with self._io_lock:
            if self._device is None:
                return None
            try:
                frame = self._send_raw(
                    protocol.build_direct_mode_status(),
                    expect="same_type",
                    timeout_ms=ACK_TIMEOUT_MS,
                )
            except SoundBlasterG8Error as exc:
                _log(f"Lecture du Direct Mode impossible: {exc}")
                return None

        if frame is None:
            _log("Lecture du Direct Mode : aucune réponse")
            return None
        return frame.direct_mode_enabled

    # ------------------------------------------------------------------
    # Mode sonore / égaliseur (confirmé par les captures « Sound Mode »)
    # ------------------------------------------------------------------

    def set_sound_mode_param(self, param: int, value: float) -> bool:
        """Envoie une écriture CMD_SET_FLOAT unique et vérifie l'ACK."""
        if self._device is None:
            _log(f"[simulation] SET_FLOAT param=0x{param:02x} value={value}")
            return False

        try:
            # build_set_float() retourne une trame déjà complète (comme
            # build_direct_mode()) : passer par _send_raw directement, pas
            # par send_frame() qui re-wrapperait le payload dans une trame.
            ack = self._send_raw(protocol.build_set_float(param, value), expect="ack")
        except SoundBlasterG8Error as exc:
            _log(f"ERREUR SET_FLOAT param=0x{param:02x}: {exc}")
            return False

        if ack is None or ack.ack_command != protocol.CMD_SET_FLOAT or not ack.ack_ok:
            _log(
                f"AVERTISSEMENT: pas d'ACK valide pour param=0x{param:02x} "
                f"({ack.describe() if ack else 'timeout'})"
            )
            return False
        return True

    def set_sound_mode(self, writes: list[tuple[int, float]]) -> bool:
        """Rejoue une séquence d'écritures CMD_SET_FLOAT (un mode sonore).

        L'ordre de la séquence est celui de la capture USB d'origine (voir
        :mod:`soundblaster_g8.sound_modes`) : il doit être préservé tel quel.
        Contrairement au Direct Mode, ces écritures ne provoquent pas de reset
        USB de la carte.

        Returns:
            ``True`` seulement si **toutes** les écritures ont été acquittées.
        """
        _log(f"Mode sonore : envoi de {len(writes)} paramètre(s)")
        with self._io_lock:
            all_ok = True
            for param, value in writes:
                if not self.set_sound_mode_param(param, value):
                    all_ok = False
            _log(f"Mode sonore {'appliqué' if all_ok else 'partiellement appliqué'}")
            return all_ok

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
