# RootLens

RootLens is a graph-grounded autonomous incident diagnosis and remediation
platform. It investigates distributed-system failures through verifiable
metrics, traces, logs, topology, and change evidence.

This repository is being delivered incrementally. Milestones 1–3 established a
reproducible observability stack, provenance-preserving telemetry gateway, and
trace-derived service graph. Milestone 4 adds controlled fault injection; it
intentionally does not contain agent or remediation logic.

## Milestone 1 stack

- OpenTelemetry Demo 3.0.0, pinned as a Git submodule
- OpenTelemetry Collector
- Prometheus
- Tempo with service-graph and span-metrics generation
- Loki with native OTLP log ingestion
- Grafana with provisioned data sources
- PostgreSQL 18
- Python 3.12 and a FastAPI application skeleton
- Locked Python runtime and development dependencies

## Milestone 2 gateway

- Async Prometheus/PromQL, Tempo/TraceQL, and Loki/LogQL clients
- Read-only Kubernetes workload and Event client
- Typed normalized evidence with query provenance on every result
- Finite timeouts, bounded retries and concurrency, and response-size limits
- Explicit typed failures with safe error messages
- Least-privilege Kubernetes RBAC with no write verbs

## Milestone 3 service graph

- Automatic caller-to-callee topology reconstruction from Tempo traces
- Per-edge traffic, failure, latency percentile, and observation metadata
- Deterministic dependency, caller, and shortest-path traversal with NetworkX
- Immutable, evidence-linked graph snapshots persisted in PostgreSQL
- HTTP endpoints for graph rebuilding and exploration

## Milestone 4 fault injection

- Pinned kind cluster, OpenTelemetry Demo Helm chart, and Chaos Mesh release
- Five reproducible faults: pod kill, CPU stress, network latency, packet loss,
  and HTTP delay
- Host-only experiment controller with target checks, server-side dry runs,
  bounded durations, and fail-safe cleanup reporting
- Append-only hidden ground truth with restrictive filesystem permissions
- A redacted public receipt that never exposes the fault or target

## Quick start

Prerequisites are Git, Python 3.12, Docker Desktop, and Docker Compose 2.30+.
Allocate at least 6 GB of memory to Docker Desktop for the demo environment.

```bash
make bootstrap
make check
make up
make gateway-smoke
make topology-smoke
```

`make up` starts the environment, applies the database migration, and waits for
metrics, traces, logs, and service-graph telemetry to become queryable.
It builds the RootLens API locally and runs the demo's pinned release images;
it does not rebuild the upstream polyglot services.

Endpoints:

| Component | URL |
| --- | --- |
| RootLens API | <http://localhost:8000> |
| OpenTelemetry Demo | <http://localhost:8080> |
| Prometheus | <http://localhost:9090> |
| Tempo | <http://localhost:3200> |
| Loki | <http://localhost:3100> |
| Grafana | <http://localhost:3001> |
| PostgreSQL | `localhost:5433` |

Stop the services without deleting their data:

```bash
make down
```

See [local development](docs/local-development.md) for troubleshooting and
[architecture](docs/architecture.md) for the current system boundary. The
[telemetry gateway contract](docs/telemetry-gateway.md) documents evidence,
failure, and Kubernetes access semantics. The [service graph](docs/service-graph.md)
documents reconstruction, traversal, persistence, and API semantics. The
[fault-injection runbook](docs/fault-injection.md) documents the isolated
benchmark controller and Kubernetes workflow.

## Kubernetes fault-injection environment

This mode replaces the Compose demo workloads with the Kubernetes demo while
retaining the RootLens observability backends and database:

```bash
make k8s-up
make chaos-validate
make chaos-smoke
```

The demo is exposed at <http://localhost:18080>. `chaos-smoke` performs a real,
10-second checkout pod-kill experiment and verifies its hidden lifecycle. Use
`make k8s-down` to delete the kind cluster; this does not delete Compose volumes.
