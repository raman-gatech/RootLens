# Milestone 4 architecture

```text
kind: OpenTelemetry Demo + load generator
          |                  ^
          | OTLP             | scoped Chaos Mesh faults
          v                  |
RootLens Collector     Host experiment controller
   /      |      \             |             |
Prom   Tempo   Loki       kubectl apply   hidden journal
   \      |      /                            (0700/0600)
    Telemetry Gateway <------- Kubernetes API (GET only)
             |
    Service Graph Builder
             |
  NetworkX + PostgreSQL <------- RootLens API
```

The OpenTelemetry Demo remains pinned as an upstream Git submodule for Compose.
The Kubernetes environment pins its Helm chart and application version. RootLens
owns the collector and backend configurations, so telemetry contracts do not
depend on the demo's bundled Jaeger/OpenSearch observability layer.

The collector is the only application telemetry ingress. It exports metrics to
a Prometheus scrape endpoint, traces to Tempo over OTLP/gRPC, and logs to Loki's
native OTLP endpoint. Tempo generates service-graph and span metrics and writes
them to Prometheus.

The gateway is an anti-corruption layer over each backend's HTTP API. It retains
query provenance and turns external payloads into shared typed evidence. It does
not correlate evidence or make causal claims.

The service graph builder deterministically creates caller-to-callee edges from
cross-service parent/child span relationships. Persisted graph snapshots retain
the exact telemetry evidence references used to construct them.

The experiment controller is a separate host-only package. It writes complete
fault truth to a permission-restricted journal outside the repository and
returns only a redacted lifecycle receipt. It is not copied into the RootLens
runtime image, and the RootLens Kubernetes identity retains GET-only access.

Milestone 4 deliberately excludes incident domain models, anomaly detection,
agents, causal ranking, and remediation.
