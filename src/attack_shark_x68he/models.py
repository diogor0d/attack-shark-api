from dataclasses import dataclass

VID = 0x3151
PID = 0x502D
ALLOWED_INTERNAL_IDS = frozenset({2270, 2472, 2902})


@dataclass(frozen=True)
class Led:
    index: int
    name: str
    row: int
    column: int
    matrix_slot: int | None = None


@dataclass(frozen=True)
class DeviceIdentity:
    vendor_id: int
    product_id: int
    internal_id: int
    revision: int | None = None


@dataclass(frozen=True)
class LightingState:
    mode: int
    speed: int = 0
    brightness: int = 0
    option: int = 0
    flags: int = 0
    rgb: tuple[int, int, int] = (0, 0, 0)
