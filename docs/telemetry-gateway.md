# Milestone 2 telemetry gateway

The telemetry gateway is the evidence-access boundary for RootLens. It provides
asynchronous clients for Prometheus, Tempo, Loki, and the Kubernetes API. It
normalizes backend payloads but does not diagnose incidents, rank causes, or
execute actions.

## Evidence contract

Every successful query returns a typed `TelemetryEnvelope` containing:

- an explicit success status;
- the backend source and exact query or API path;
- every query parameter and, when applicable, the UTC collection window;
- the UTC retrieval timestamp and a SHA-256-backed `telemetry://` reference;
- normalized metric series, log streams, trace summaries/spans, or Kubernetes
  state; and
- warnings when a source has important reliability semantics.

Backend failures raise `TelemetryQueryError` with a source, error code, HTTP
status when available, and retryability. Response bodies are deliberately not
copied into error messages because they can contain sensitive data.

## Reliability boundaries

Clients use finite timeouts, bounded exponential retries for transport errors,
HTTP 429, and HTTP 5xx, a concurrency semaphore, and a maximum response size.
HTTP 4xx responses other than 429 are not retried. Malformed or unsupported
backend payloads fail explicitly instead of producing placeholder evidence.

## Kubernetes access

`KubernetesClient` exposes only list operations implemented with HTTP GET. The
tracked RBAC manifest grants only `get`, `list`, and `watch` for Pods, Events,
Deployments, and ReplicaSets. It grants no write verbs, Secret access, or
subresource access.

Kubernetes Events are best-effort, supplemental records. Change-event
normalization preserves that warning and never treats an Event as proof of
causality.

## Verification

With the Milestone 1 stack running:

```bash
make gateway-smoke
```

This executes PromQL, LogQL, and TraceQL queries through the production clients,
then retrieves and normalizes one complete trace. Kubernetes is contract-tested
with a mock API until the Kubernetes deployment milestone.
