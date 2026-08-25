"""Service-topology domain failures."""


class TopologyError(RuntimeError):
    """Base error for deterministic topology operations."""


class TopologyBuildError(TopologyError):
    """Raised when a graph cannot be reconstructed from available evidence."""


class ServiceNotFoundError(TopologyError):
    """Raised when a traversal starts from a service absent from the graph."""


class ServicePathNotFoundError(TopologyError):
    """Raised when no directed dependency path connects two services."""
