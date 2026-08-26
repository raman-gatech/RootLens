# Changelog

All notable changes are documented here. RootLens follows semantic versioning.

## 1.0.1 — 2026-08-26

- Add a protected, phased production deployment workflow with immutable-signature
  verification, secret/TLS/database validation, migration-before-rollout ordering,
  public readiness/authentication checks, and aggregate deployment evidence.
- Add strict rendering for hostname, telemetry, ingress, monitored-namespace, and
  image-digest inputs; scope Kubernetes observation RBAC to one namespace.
- Add real OpenAI live baselines with pinned model pricing, blinded inputs, strict
  structured output, transient API retries, and aggregate-only publishing.
- Publish the completed 100-incident deterministic live evaluation and harden the
  Chaos Mesh controller/evidence path used by live studies.

## 1.0.0 — 2026-08-25

- Complete the twelve-milestone graph-grounded investigation platform.
- Add statistical and Isolation Forest anomaly detection.
- Add sequential and parallel specialist-agent investigation with audited tools,
  evidence UUIDs, deterministic causal ranking, adversarial verification, and
  pgvector incident memory.
- Add the operator dashboard, guarded remediation workflow, twenty-family Chaos
  Mesh catalog, and reproducible 100-case evaluation harness.
- Add production bearer authentication with function-level permissions and
  authenticated approval identity binding.
- Harden runtime images, readiness, local network exposure, Kubernetes templates,
  CI, dependency auditing, static security analysis, and browser regression tests.
