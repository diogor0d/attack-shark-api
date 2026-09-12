import os
import threading
from contextlib import contextmanager

from .errors import DeviceBusyError

_lock = threading.Lock()
_owners: set[str] = set()
_named_owners: set[str] = set()
_mutexes_guard = threading.Lock()


@contextmanager
def named_mutex(name: str):
    """Acquire an OS-wide mutex on Windows, or a process-safe test mutex elsewhere."""
    with _mutexes_guard:
        if name in _named_owners:
            raise DeviceBusyError(f"device mutex {name} is already owned")
        _named_owners.add(name)
    try:
        if os.name != "nt":
            yield
            return

        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.CreateMutexW(None, False, name)
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateMutexW failed")
        acquired = False
        try:
            wait_result = kernel32.WaitForSingleObject(handle, 0)
            if wait_result not in {0x00000000, 0x00000080}:
                raise DeviceBusyError(f"device mutex {name} is already owned")
            acquired = True
            yield
        finally:
            if acquired:
                kernel32.ReleaseMutex(handle)
            kernel32.CloseHandle(handle)
    finally:
        with _mutexes_guard:
            _named_owners.discard(name)


@contextmanager
def claim(device_id: str):
    with named_mutex(f"Global\\AttackSharkX68HE-{device_id}"):
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
