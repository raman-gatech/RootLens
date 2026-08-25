# Milestone 5 anomaly detection

Milestone 5 ranks anomalous service/signal pairs using an interpretable
statistical baseline and a deterministic Isolation Forest. It consumes only
provenance-bearing Prometheus results and has no access to experiment ground
truth. It does not make causal claims or choose a root cause.

## Input contract

An analysis compares two non-overlapping, UTC-aware windows:

- The baseline window represents normal behavior and must end before or exactly
  when the incident window starts.
- The incident window contains the behavior being evaluated.

The initial signal catalog uses service-graph metrics that are uniformly
available across the polyglot OpenTelemetry Demo:

| Signal | Prometheus source | Unit |
| --- | --- | --- |
| `request_rate` | rate of server-side service-graph requests | requests/second |
| `error_rate` | failed requests divided by all requests | ratio |
| `p95_latency` | server-side service-graph latency histogram | milliseconds |

CPU, memory, network, and restart features remain future catalog additions.
Their instrumentation is not currently uniform across every demo service, so
silently filling them with zero would make the model misleading.

## Statistical baseline

Each service/signal series records baseline mean, population standard deviation,
median, median absolute deviation (MAD), and final exponentially weighted moving
average (EWMA). Every incident point is evaluated using:

- robust z-score based on scaled MAD;
- conventional z-score;
- EWMA forecast residual.

The maximum magnitude becomes a bounded score in `[0, 1]`. A score of `0.5`
corresponds to a three-standard-deviation-equivalent deviation, and the first
point crossing that level is recorded as `anomaly_start_time`. Zero-variance
baselines explicitly distinguish unchanged values from real changes.

## Isolation Forest

Signals with common timestamps form a multivariate feature matrix per service.
Features are robustly scaled from baseline medians and MAD, constant columns are
removed, and an Isolation Forest with 100 estimators, `random_state=42`, and one
worker is fitted for that analysis. Its raw abnormality is calibrated as an
empirical percentile against baseline scores.

The final service/signal score is 70% statistical attribution and 30% service
Isolation Forest context. If aligned multivariate data is insufficient, the
statistical result is retained and a warning explains why the forest was
skipped. Stable sorting makes ties reproducible.

Models are trained in memory for each immutable analysis and are not deserialized
from pickle/joblib artifacts. The persisted snapshot instead records algorithm
version, baseline statistics, scores, anomaly onset, telemetry references, and
warnings. This avoids executable model-file input and retains the information
needed to reproduce a result from telemetry.

## API

```text
POST /api/v1/anomalies/analyze
GET  /api/v1/anomalies/latest
```

Example request:

```json
{
  "baseline_start": "2026-08-25T14:00:00Z",
  "baseline_end": "2026-08-25T14:20:00Z",
  "incident_start": "2026-08-25T14:20:00Z",
  "incident_end": "2026-08-25T14:25:00Z",
  "signals": ["request_rate", "error_rate", "p95_latency"],
  "step_seconds": 30,
  "minimum_score": 0.5
}
```

The response is ranked by descending score and then deterministic temporal/name
tie-breakers. Every anomaly carries the Prometheus evidence references used to
produce it. Baseline and incident sample counts are bounded at the API boundary,
and CPU-bound forest fitting runs outside the asynchronous request loop. Complete
snapshots are stored in the `telemetry_anomalies` table.

For a recent live window:

```bash
make anomaly-smoke
```

This command evaluates and persists recent telemetry. It fails if no series or
ranked anomaly exists, if ranks are discontinuous, if scores are unordered, or
if provenance is not exclusively Prometheus-backed.
