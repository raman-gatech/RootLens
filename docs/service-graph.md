# Milestone 3 service graph

RootLens reconstructs service topology from complete distributed traces. It does
not use a hardcoded service list or treat Tempo's generated service-graph metrics
as topology ground truth.

## Reconstruction rule

For each trace, spans are indexed by `(trace_id, span_id)`. A directed edge is
created when a span and its parent have different non-empty `service.name`
resources:

```text
parent service -> child service
```

Same-service parent/child relationships remain internal implementation detail
and are excluded. Missing parents are ignored rather than guessed.

Every edge aggregates:

- request and distinct-trace counts;
- failures and error rate;
- requests per second over the collection window;
- p50, p95, and p99 child-span latency; and
- first and last observation timestamps.

Every node records span, trace, and error counts. Each immutable snapshot retains
its UTC query window and all Tempo search/trace evidence references.

## Traversal semantics

Edges point from caller to callee. Therefore:

- descendants are transitive dependencies worth investigating for an impacted
  upstream service;
- ancestors are upstream callers potentially affected by a failing dependency;
- shortest paths explain a concrete propagation route.

Cycles are allowed because real service systems are not guaranteed to be DAGs.
Traversal uses a directed NetworkX graph and never infers unobserved edges.

## Persistence and API

Snapshots are stored in PostgreSQL as versioned JSON documents with indexed
generation timestamps and denormalized counts. The API supports:

```text
POST /api/v1/topology/rebuild
GET  /api/v1/topology/latest
GET  /api/v1/topology/latest/services/{service}/dependencies
GET  /api/v1/topology/latest/services/{service}/callers
GET  /api/v1/topology/latest/path?source=...&target=...
```

Run the end-to-end acceptance check after starting the stack:

```bash
make topology-smoke
```
