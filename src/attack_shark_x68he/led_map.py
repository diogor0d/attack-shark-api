from .models import Led

_CAPTURED_MATRIX_SLOTS = {
    "escape": 1,
    "a": 9,
    "space": 41,
    "arrow_right": 89,
}

_ROWS = [
    (
        0,
        [
            "escape",
            *[f"digit{i}" for i in range(1, 10)],
            "digit0",
            "minus",
            "equal",
            "backspace",
            "delete",
        ],
    ),
    (1, ["tab", *list("qwertyuiop"), "bracket_left", "bracket_right", "backslash", "page_up"]),
    (2, ["caps_lock", *list("asdfghjkl"), "semicolon", "quote", "enter", "page_down"]),
    (3, ["shift_left", *list("zxcvbnm"), "comma", "period", "slash", "shift_right", "arrow_up"]),
    (
        4,
        [
            "control_left",
            "meta_left",
            "alt_left",
            "space",
            "fn",
            "control_right",
            "arrow_left",
            "arrow_down",
            "arrow_right",
        ],
    ),
]
LED_MAP = tuple(
    Led(i, name, row, col, _CAPTURED_MATRIX_SLOTS.get(name))
    for row, names in _ROWS
    for col, name in enumerate(names)
    for i in [sum(len(x[1]) for x in _ROWS[:row]) + col]
)
assert len(LED_MAP) == 66
MAPPING_VERIFIED = False


def led_by_name(name: str) -> Led:
    for led in LED_MAP:
        if led.name == name:
            return led
    raise KeyError(name)
