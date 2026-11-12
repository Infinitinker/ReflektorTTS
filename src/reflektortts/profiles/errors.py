"""Errors in addressing a profile and its parts: a profile that does not exist or cannot be read,
and a source or stage it does not have."""


class SourceError(Exception):
    """A source cannot be switched on or off; the message says why."""


class StageError(Exception):
    """A stage cannot be switched on or off; the message says why."""


class UnknownProfileError(Exception):
    """There is no profile with that ID."""


class BrokenProfileError(Exception):
    """A profile's file cannot be read, so it has no settings to show or change."""
