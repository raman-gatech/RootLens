# RootLens 1.0 architecture

```text
OpenTelemetry Demo / Kubernetes
        | OTLP                         host-only benchmark truth
        v                                      |
Collector -> Prometheus / Tempo / Loki         | never mounted or served
                    |                           v
              Telemetry Gateway        Evaluation Harness
                    |
       +------------+-------------+
       |            |             |
 Anomaly Engine  Trace Graph  K8s read client
       +------------+-------------+
                    |
       audited, typed Evidence objects
                    |
 metrics / trace / log / change specialists (parallel)
                    |
        manager + pgvector priors
                    |
      deterministic causal ranker
                    |
          adversarial verifier
                    |
 PostgreSQL <- Incident API -> Operator Console
                    |
     independent remediation policy
                    |
      explicit approval + atomic execution claim
                    |
 fixed Level-1 pod executor / Level-2+ advice only
```

## Trust boundaries

The telemetry gateway preserves each backend query, window, retrieval time, and
content-addressed reference. It normalizes observations but never makes causal
claims. Logs are untrusted input: collectors retain bounded categories and
counts and never treat log text as instructions.

The host-only `experiment_controller` owns complete fault truth. Docker copies
only `src`, so neither it nor `evaluation_harness` exists in the runtime image.
Runtime evaluation records contain aggregates only, preventing diagnostic code
from reading an answer from a manifest, process argument, or database row.

Production API requests cross an identity boundary before routing. Opaque
bearer tokens are checked against digest-only credentials and mapped to
individual principals with function-level `read`, `investigate`, `ingest`,
`publish`, and `remediate` permissions. Remediation decisions must name the
authenticated principal. Health probes and the static dashboard shell remain
unauthenticated; all incident data and actions are protected under `/api/v1`.

## Investigation flow

Single-agent mode calls four allowlisted evidence tools sequentially. Multi-
agent mode uses `asyncio.gather` for metrics, traces, logs, and changes. The
manager receives typed evidence only; memory adds up to five historical priors.
The verifier removes unknown evidence references and rejects a positive claim
with no current support.

The optional OpenAI adapter calls `POST /v1/responses`, disables storage, asks
for strict JSON Schema output, validates with Pydantic, and filters every cited
ID against the ledger. Collection, causal math, verification, and policy remain
outside the model.

## Causal ranking

| Feature | Weight |
| --- | ---: |
| anomaly strength | 0.25 |
| temporal precedence | 0.20 |
| trace criticality | 0.20 |
| graph consistency | 0.15 |
| log evidence | 0.10 |
| recent change | 0.05 |
| historical similarity | 0.05 |

Contradiction applies an additional penalty. Historical similarity can shift a
prior but is always excluded from `evidence_for`.

## Persistence and remediation

PostgreSQL stores alerts, incidents, investigations, evidence, hypotheses, agent runs,
tool calls, graph/anomaly snapshots, 128-dimensional pgvector memory,
remediation plans/actions, and aggregate evaluation reports.

The diagnostic agent cannot mutate Kubernetes. A separate policy checks
namespace and exact target syntax, current evidence, diagnosis confidence,
action risk, named approval, and live pod ownership. Only `restart_pod` for a
ReplicaSet-owned pod can pass. Atomic `proposed -> approved -> executing`
transitions prevent double execution. The executor exposes one positional
`kubectl delete pod` operation and no shell, selector, or arbitrary command.
