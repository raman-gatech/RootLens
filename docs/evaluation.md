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

The checked-in `docs/evaluation-live-results.json` is a separate completed run of
100 wall-clock Chaos Mesh experiments. Every experiment reached
`AllInjected=True` and then recovery before RootLens investigated it. This run
used the deterministic provider and therefore proves the live control,
telemetry, isolation, and aggregation path, but it is not paid-model evidence.

## Real OpenAI study

The manually dispatched `OpenAI Live Evaluation` workflow runs the same 20 fault
families five times and compares:

- A: alert-only, with no model or telemetry tools;
- B: one Responses API call with only the blinded alert;
- C: one Responses API call over retrieved live evidence;
- D: concurrent metrics, trace, log, and change/context specialists;
- E: the same specialist outputs plus RootLens graph-causal ranking and evidence
  verification.

The workflow pins `gpt-5.4-mini-2026-03-17`, uses strict Structured Outputs,
disables response storage, retries transient 408/409/429/5xx failures, and
calculates cost from the published $0.75/M input and $4.50/M output token prices.
D and E intentionally share the same specialist calls so their comparison
isolates RootLens graph ranking and verification. Complete truth remains only in
the protected journal and is attached after predictions for metric reduction.
Only aggregate `EvaluationReport` objects may be published; neither the report
nor the API exposes case predictions or hidden answers.

To run it, create `OPENAI_API_KEY` in the protected GitHub environment named
`production`, then dispatch `OpenAI Live Evaluation` on `main`. The key is copied
to a mode-0600 runner file, never passed as a command-line argument, removed in
the unconditional cleanup, and never committed. The workflow refuses to start
infrastructure if the secret is absent. Its final gate requires 100 trials for
all five methods, nonzero real model calls/tokens/costs for B–E, 100 recovered
ground-truth lifecycles, and no serialized `ground_truth` field. Model access,
account rate limits, and spend limits must be confirmed before dispatch. Current
model capabilities and pricing are documented at
<https://developers.openai.com/api/docs/models/gpt-5.4-mini>.

## Reproducibility

The dataset uses stable timestamps, UUIDv5 identifiers, feature values, and
SHA-256 seeds. Accuracy and evidence metrics are deterministic. Runtime latency,
report UUID, and generation time are observed per run. Private case contracts
live outside `src` and therefore outside the RootLens API image.
