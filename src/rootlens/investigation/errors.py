"""Investigation-domain failures."""


class InvestigationError(RuntimeError):
    """A bounded investigation could not complete."""


class IncidentNotFoundError(InvestigationError):
    """The requested incident does not exist."""


class ProviderError(InvestigationError):
    """The configured hypothesis provider returned an invalid result."""
