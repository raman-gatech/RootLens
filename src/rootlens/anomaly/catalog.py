"""PromQL definitions for service-wide signals available from Tempo metrics."""

from pydantic import BaseModel, ConfigDict

from rootlens.anomaly.contracts import SignalName


class SignalDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    signal: SignalName
    promql: str
    service_label: str


SIGNAL_CATALOG: dict[SignalName, SignalDefinition] = {
    SignalName.REQUEST_RATE: SignalDefinition(
        signal=SignalName.REQUEST_RATE,
        promql=('sum by (server) (rate(traces_service_graph_request_total{server!=""}[1m]))'),
        service_label="server",
    ),
    SignalName.ERROR_RATE: SignalDefinition(
        signal=SignalName.ERROR_RATE,
        promql=(
            'sum by (server) (rate(traces_service_graph_request_failed_total{server!=""}[1m])) '
            "/ clamp_min(sum by (server) "
            '(rate(traces_service_graph_request_total{server!=""}[1m])), 0.000000001)'
        ),
        service_label="server",
    ),
    SignalName.P95_LATENCY: SignalDefinition(
        signal=SignalName.P95_LATENCY,
        promql=(
            "histogram_quantile(0.95, sum by (server, le) "
            '(rate(traces_service_graph_request_server_seconds_bucket{server!=""}[1m]))) '
            "* 1000"
        ),
        service_label="server",
    ),
}
