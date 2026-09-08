import threading
from contextlib import contextmanager

from .errors import DeviceBusyError

_lock = threading.Lock()
_owners: set[str] = set()


@contextmanager
def claim(device_id: str):
    with _lock:
        if device_id in _owners:
            raise DeviceBusyError(f"device {device_id} is already owned")
        _owners.add(device_id)
    try:
        yield
    finally:
        with _lock:
            _owners.discard(device_id)


def owner_present(device_id: str) -> bool:
    with _lock:
        return device_id in _owners
