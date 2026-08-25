"""Safe anomaly-analysis failures exposed at the service boundary."""


class AnomalyAnalysisError(RuntimeError):
    pass
