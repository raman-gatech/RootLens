# Remediation safety runbook

Execution is off by default. Diagnosis and recommendation remain available when
`ROOTLENS_REMEDIATION_EXECUTION_ENABLED=false`.

| Level | Examples | Behavior |
| --- | --- | --- |
| 0 | telemetry and topology reads | always read-only |
| 1 | restart one exact stateless pod | approval, revalidation, optional execution |
| 2 | scale, rollback, deployment restart | recommendation only |
| 3 | database, secret, network-policy change | prohibited / recommendation only |

Propose with `POST /api/v1/incidents/{id}/remediation`. Payloads contain an
enumerated action, DNS-safe namespace, exact resource name (never a selector),
target service, and rationale. RootLens cites the top hypothesis's current
evidence automatically.

Approve or reject with `POST /api/v1/incidents/{id}/approve-remediation` or
`reject-remediation`; both require `plan_id`, named `actor`, and `reason`.
When production authentication is enabled, the supplied actor must exactly
match the authenticated principal; the API rejects spoofed approval identity.
Approval immediately re-reads the target and requires:

- proposal policy still passes;
- the approved investigation is current;
- namespace and pod name exactly match;
- the pod owner is a ReplicaSet, not a StatefulSet;
- an atomic state transition claims execution once.

The receipt records plan/incident IDs, exact target, timestamps, status,
executor, and bounded output. The executor never uses a shell. Failed checks are
persisted without attempting a broader action.

Prompt-injection tests cover command-like targets and historical-only support.
Exact-name regexes, typed actions, positional subprocess arguments, and an
independent policy prevent log or model text from becoming commands.

`make k8s-up` supplies the diagnostic provider with a local `rootlens-reader`
token that can only read pod metadata. It deliberately cannot execute a restart.
For a disposable kind remediation acceptance test, execute from a separate,
named host operator context after explicit approval. Never give the diagnostic
provider Kubernetes mutation credentials.
