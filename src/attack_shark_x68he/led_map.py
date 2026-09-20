from .models import Led

# Derived from the internal-ID-2902 default matrix shipped in Attack Shark
# Driver v4 3.1.12. The four sparse-capture anchors match exactly:
# escape=1, a=9, space=41, arrow_right=89.
_MATRIX_SLOTS = {
    "escape": 1,
    "digit1": 7,
    "digit2": 13,
    "digit3": 19,
    "digit4": 25,
    "digit5": 31,
    "digit6": 37,
    "digit7": 43,
    "digit8": 49,
    "digit9": 55,
    "digit0": 61,
    "minus": 67,
    "equal": 73,
    "backspace": 79,
    "delete": 85,
    "tab": 2,
    "q": 8,
    "w": 14,
    "e": 20,
    "r": 26,
    "t": 32,
    "y": 38,
    "u": 44,
    "i": 50,
    "o": 56,
    "p": 62,
    "bracket_left": 68,
    "bracket_right": 74,
    "backslash": 80,
    "page_up": 86,
    "caps_lock": 3,
    "a": 9,
    "s": 15,
    "d": 21,
    "f": 27,
    "g": 33,
    "h": 39,
    "j": 45,
    "k": 51,
    "l": 57,
    "semicolon": 63,
    "quote": 69,
    "enter": 81,
    "page_down": 87,
    "shift_left": 4,
    "z": 16,
    "x": 22,
    "c": 28,
    "v": 34,
    "b": 40,
    "n": 46,
    "m": 52,
    "comma": 58,
    "period": 64,
    "slash": 70,
    "shift_right": 76,
    "arrow_up": 82,
    "control_left": 5,
    "meta_left": 11,
    "alt_left": 17,
    "space": 41,
    "fn": 65,
    "control_right": 71,
    "arrow_left": 77,
    "arrow_down": 83,
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
    Led(i, name, row, col, _MATRIX_SLOTS[name])
    for row, names in _ROWS
    for col, name in enumerate(names)
    for i in [sum(len(x[1]) for x in _ROWS[:row]) + col]
)
assert len(LED_MAP) == 66
assert len(_MATRIX_SLOTS) == len(LED_MAP)
assert len(set(_MATRIX_SLOTS.values())) == len(LED_MAP)
MAPPING_VERIFIED = True


def led_by_name(name: str) -> Led:
    for led in LED_MAP:
        if led.name == name:
            return led
    raise KeyError(name)
