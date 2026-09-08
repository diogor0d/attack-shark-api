"""Show deterministic full-screen colour patches for mode-21 USB captures."""

from __future__ import annotations

import tkinter as tk
from time import monotonic

PATCHES = (
    ("red", "#ff0000", 5_000),
    ("black-separator", "#000000", 2_000),
    ("green", "#00ff00", 5_000),
    ("black-separator", "#000000", 2_000),
    ("blue", "#0000ff", 5_000),
    ("black-separator", "#000000", 2_000),
    ("white", "#ffffff", 5_000),
    ("black", "#000000", 5_000),
)


def main() -> None:
    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.attributes("-topmost", True)
    root.configure(cursor="none")
    root.bind("<Escape>", lambda _event: root.destroy())
    started = monotonic()

    def show(index: int) -> None:
        if index == len(PATCHES):
            print(f"PATCH complete t={monotonic() - started:.3f}", flush=True)
            root.destroy()
            return
        name, colour, duration_ms = PATCHES[index]
        root.configure(background=colour)
        print(f"PATCH {name} t={monotonic() - started:.3f}", flush=True)
        root.after(duration_ms, show, index + 1)

    root.after(3_000, show, 0)
    root.mainloop()


if __name__ == "__main__":
    main()
