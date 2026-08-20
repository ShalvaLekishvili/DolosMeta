"""Expected engine errors; parser errors are normally converted to partial results."""


class DolosMetaError(Exception):
    """Base error for controlled DolosMeta failures."""


class BoundsError(DolosMetaError):
    """A parser attempted to read outside its bounded source."""


class LimitExceeded(DolosMetaError):
    """A configured analysis budget was exhausted."""


class MalformedFile(DolosMetaError):
    """Input violates the expected format structure."""


class AnalysisTimeout(DolosMetaError):
    """The wall-clock analysis limit expired."""

