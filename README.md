# RootLens

RootLens is a graph-grounded incident diagnosis and guarded-remediation
platform. Version 1.0 implements the complete twelve-milestone plan through
verifiable telemetry, deterministic causal ranking, and explicit safety policy.

## Capabilities

- Pinned OpenTelemetry Demo, Collector, Prometheus, Tempo, Loki, Grafana,
  PostgreSQL 18/pgvector, Python 3.12, and FastAPI stack
- Provenance-preserving async telemetry gateway with bounded retries, response
  sizes, concurrency, and read-only Kubernetes access
- Trace-derived service graph and MAD/z-score/EWMA plus Isolation Forest anomaly
  ranking
- Host-only Chaos Mesh controller with 20 pod, stress, network, HTTP, DNS, I/O,
  and clock fault families and isolated ground truth
- Sequential single-agent baseline plus parallel metrics, trace, log, change,
  memory, manager, and adversarial verifier agents
- Structured hypotheses whose positive claims must cite stored evidence UUIDs
- Deterministic anomaly/temporal/graph/log/change/memory causal scoring
- PostgreSQL/pgvector incident memory; historical matches are typed priors and
  cannot prove current facts
- Optional OpenAI Responses API strict-schema synthesis with a deterministic
  offline provider as the default
- Responsive operator console with hypotheses, graph, evidence, timeline,
  agent trace, and remediation views
- Independent remediation policy, explicit named approval, atomic execution
  claims, and a single exact stateless-pod restart as the only executable action
- Reproducible 100-case evaluation with five methods, seven ablations, accuracy,
  evidence, latency, resource, cost, and safety metrics

## Quick start

Prerequisites are Git, Python 3.12, Docker Desktop, and Docker Compose 2.30+.
Allocate at least 8 GB of memory for Kubernetes mode.

```bash
make bootstrap
make check
make up
make gateway-smoke
make topology-smoke
make anomaly-smoke
make benchmark
```

`make up` builds RootLens, waits for observability, applies every migration, and
runs readiness checks. Defaults require no model key and keep remediation
execution disabled.

| Component | URL |
| --- | --- |
| RootLens console | <http://localhost:8000/dashboard> |
| RootLens API / OpenAPI | <http://localhost:8000/docs> |
| OpenTelemetry Demo | <http://localhost:8080> |
| Prometheus | <http://localhost:9090> |
| Tempo | <http://localhost:3200> |
| Loki | <http://localhost:3100> |
| Grafana | <http://localhost:3001> |
| PostgreSQL | `localhost:5433` |

Stop services without deleting data with `make down`.

## Kubernetes fault environment

```bash
make k8s-up
make chaos-validate
make chaos-smoke
```

The demo is exposed at <http://localhost:18080>. `chaos-validate` sends all 20
manifests through Kubernetes server-side validation. `chaos-smoke` runs one
real, 10-second disposable pod kill and verifies the protected lifecycle.

## Documentation

- [Architecture and trust boundaries](docs/architecture.md)
- [Local development](docs/local-development.md)
- [Telemetry gateway](docs/telemetry-gateway.md)
- [Service graph](docs/service-graph.md)
- [Fault injection](docs/fault-injection.md)
- [Anomaly detection](docs/anomaly-detection.md)
- [Incident agents and evidence](docs/investigation.md)
- [Remediation safety](docs/remediation.md)
- [Evaluation methodology](docs/evaluation.md)
- [Production deployment and security](docs/production-deployment.md)
- [Security policy](SECURITY.md)
- [Changelog](CHANGELOG.md)

RootLens is an operational-assistance system. Level 2/3 actions remain
recommendations; operators are responsible for production changes.
