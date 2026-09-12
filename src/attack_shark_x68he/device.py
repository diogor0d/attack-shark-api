import time

from .errors import DeviceBusyError, ProtocolError, UnsupportedDeviceError
from .models import PID, VID, DeviceIdentity, LightingState
from .ownership import claim
from .protocol import (
    GET_IDENTIFY,
    GET_LIGHT,
    GET_REVISION,
    encode_get,
    encode_light_preset,
    encode_screen_color,
    parse_identify,
    parse_light_state,
    parse_revision,
    validate_internal_id,
    validate_reply,
)
from .transport import HidTransport


class DeviceController:
    def __init__(
        self, transport: HidTransport, *, device_id: str = "x68he", settle_seconds: float = 0.01
    ):
        self.transport, self.device_id = transport, device_id
        self.settle_seconds = settle_seconds
        self.identity: DeviceIdentity | None = None
        self._saved_state: LightingState | None = None
        self._claim = None

    @classmethod
    def open(cls) -> "DeviceController":
        return cls(HidTransport.open())

    def _exchange(self, opcode: int) -> bytes:
        self.transport.write(encode_get(opcode))
        if self.settle_seconds:
            time.sleep(self.settle_seconds)
        deadline = time.monotonic() + 0.5
        last_async: int | None = None
        while True:
            report = self.transport.read()
            if report and report[0] == opcode:
                return validate_reply(report, opcode)
            if report and report[0] not in {0x0D, 0x0E}:
                return validate_reply(report, opcode)
            if report:
                last_async = report[0]
            if time.monotonic() >= deadline:
                if last_async is not None:
                    raise DeviceBusyError(
                        "host-driven lighting reports are active; close other lighting software"
                    )
                raise ProtocolError(f"timed out waiting for reply opcode 0x{opcode:02X}")
            time.sleep(0.01)

    def probe(self) -> DeviceIdentity:
        internal = validate_internal_id(parse_identify(self._exchange(GET_IDENTIFY)))
        revision = parse_revision(self._exchange(GET_REVISION))
        self.identity = DeviceIdentity(VID, PID, internal, revision)
        return self.identity

    def current_state(self) -> LightingState:
        self._require_identity()
        return parse_light_state(self._exchange(GET_LIGHT))

    def set_preset(self, state: LightingState) -> None:
        self._require_identity()
        self.transport.write(encode_light_preset(state, identified=True))

    def acquire_global_stream(self) -> LightingState:
        """Claim the device, save its state, and select captured mode 21."""
        previous = self.acquire()
        try:
            self.set_preset(LightingState(21, 4, 4, 0, 0, previous.rgb))
            return previous
        except Exception:
            self.release()
            raise

    def set_global_color(self, rgb: tuple[int, int, int]) -> None:
        self._require_identity()
        self.transport.write(encode_screen_color(rgb, identified=True))

    def acquire(self) -> LightingState:
        self._require_identity()
        self._claim = claim(self.device_id)
        try:
            self._claim.__enter__()
            self._saved_state = self.current_state()
            return self._saved_state
        except Exception:
            self._claim.__exit__(None, None, None)
            self._claim = None
            raise

    def release(self) -> None:
        try:
            if self._saved_state is not None and self.identity is not None:
                self.set_preset(self._saved_state)
        finally:
            self._saved_state = None
            if self._claim is not None:
                self._claim.__exit__(None, None, None)
                self._claim = None

    def close(self) -> None:
        try:
            self.release()
        finally:
            self.transport.close()

    def _require_identity(self) -> None:
        if self.identity is None:
            raise UnsupportedDeviceError("probe must succeed before device access")
