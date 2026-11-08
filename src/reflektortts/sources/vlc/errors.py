"""The error the VLC source reports."""


class VlcError(Exception):
    """VLC cannot be read now; the message says why and what to do, for the user."""
