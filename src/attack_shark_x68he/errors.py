"""Errors raised by the X68HE controller."""


class X68Error(Exception):
    """Base error."""


class DeviceNotFoundError(X68Error):
    pass


class DeviceBusyError(X68Error):
    pass


class UnsupportedDeviceError(X68Error):
    pass


class ProtocolError(X68Error):
    pass


class UnsafeCommandError(X68Error):
    pass
