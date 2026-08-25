# Incident investigation contract

## API workflow

Create an incident with a timezone-aware window of 2 minutes to 24 hours:

```bash
curl -X POST http://localhost:8000/api/v1/incidents \
  -H 'content-type: application/json' \
  -d '{
    "title":"Checkout errors",
    "affected_service":"frontend-proxy",
    "severity":"sev2",
    "incident_start":"2026-08-25T12:00:00Z",
    "incident_end":"2026-08-25T12:10:00Z"
  }'
```

Then `POST /api/v1/incidents/{id}/investigate` with either
`{"mode":"single_agent"}` or `{"mode":"multi_agent"}`. Default budgets are
30 model calls, 100 tool calls, five rounds, and 300 seconds. Responses include
usage, agent runs, tool calls, evidence, hypotheses, graph, and warnings.

Read views:

- `GET /api/v1/incidents` and `GET /api/v1/incidents/{id}`
- `GET /api/v1/incidents/{id}/hypotheses`
- `GET /api/v1/incidents/{id}/evidence`
- `GET /api/v1/incidents/{id}/timeline`
- `GET /api/v1/incidents/{id}/graph`
- `GET /api/v1/incidents/{id}/similar`

Alertmanager-compatible intake is `POST /api/v1/alerts/prometheus`.

## Evidence invariants

Every evidence object has a UUID, source, observation, optional service and
window, confidence, origin, query reference, and bounded structured attributes.
Positive hypothesis states require an evidence UUID. The verifier ensures it
exists and came from the current incident. Historical matches have origin
`historical_prior`; they may suggest a weak candidate but never satisfy current
support.

Trace evidence is emitted only for dependencies with at least 5% errors or p95
latency of at least 500 ms. Normal topology remains in the graph but is not
mislabeled as root-cause support. Raw logs are isolated as untrusted content.

## Provider selection

The default `ROOTLENS_AGENT_PROVIDER=deterministic` requires no network or key.
For strict-schema model synthesis set:

```text
ROOTLENS_AGENT_PROVIDER=openai
OPENAI_API_KEY=...
ROOTLENS_OPENAI_MODEL=gpt-5.4-mini
```

If OpenAI is selected without a key, RootLens safely retains deterministic
synthesis. Telemetry collection, causal math, evidence validation, and policy
decisions remain outside the model.

## Confirmed memory

Only an explicit operator call stores a resolution:

`POST /api/v1/incidents/{id}/memory` with `root_cause_service`, `failure_mode`,
and `resolution`. Retrieval uses pgvector cosine distance over deterministic
feature-hash embeddings. This avoids an embedding-service dependency locally
while retaining reproducible similarity behavior.
