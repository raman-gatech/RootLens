# Evaluation methodology

`make benchmark` writes `docs/evaluation-results.json` from 20 Chaos Mesh fault
families with five deterministic repetitions each (100 cases). It runs:

- A: alert-only baseline;
- B: sequential single-agent offline proxy;
- C: retrieval-agent offline proxy;
- D: multi-agent evidence aggregation;
- E: RootLens causal ranker plus verifier.

It also runs `no_graph`, `no_traces`, `no_logs`, `no_anomaly`, `no_verifier`,
`no_memory`, and `single_agent` ablations. Metrics include Top-1/Top-3 accuracy,
mean/p95 ranking latency, evidence precision, hallucinated reference rate,
tool/model calls, tokens, estimated cost, and safety violations.

## Interpretation

All 20 manifests were admitted by the live Chaos Mesh 2.8.4 cluster using
Kubernetes server-side dry-run. The 100 cases are normalized evidence replay,
so the checked-in report proves dataset cardinality, deterministic ranking,
evidence accounting, aggregation, and ground-truth isolation. It does **not**
claim 100 wall-clock faults or paid model calls. The report explicitly says
`offline_deterministic_replay`; B and C are named proxies and costs are zero
because no `OPENAI_API_KEY` was present.

A live study can reuse the schemas and aggregate publisher after running the
host controller 100 times. Complete truth stays in its protected journal. Only
aggregate `EvaluationReport` objects may be sent to `POST /api/v1/evaluations`;
`GET /api/v1/evaluations` never returns a fault target or case answer.

## Reproducibility

The dataset uses stable timestamps, UUIDv5 identifiers, feature values, and
SHA-256 seeds. Accuracy and evidence metrics are deterministic. Runtime latency,
report UUID, and generation time are observed per run. Private case contracts
live outside `src` and therefore outside the RootLens API image.
