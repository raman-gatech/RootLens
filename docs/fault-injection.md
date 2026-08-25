# Milestone 4 fault-injection runbook

The fault harness provides a reproducible Kubernetes environment and twenty
controlled Chaos Mesh experiment families. It creates labeled evaluation data;
RootLens never receives the labels.

## Pinned environment

| Component | Version |
| --- | --- |
| kind | 0.32.0 |
| Kubernetes node | 1.34.0, pinned by image digest |
| OpenTelemetry Demo Helm chart | 0.41.0 (application 3.0.0) |
| Chaos Mesh | 2.8.4 |

`make k8s-up` verifies or downloads kind and Helm into `.tools/bin`, stops the
Compose demo without deleting its volumes, starts only the RootLens database and
observability services, creates the cluster, installs both charts, and runs the
acceptance checks. The Kubernetes collector forwards OTLP telemetry to the
RootLens collector on the Docker host. The demo frontend is available at
<http://localhost:18080>.

The same command creates a namespace-scoped, read-only `rootlens-reader`
service account and exports only its token and cluster CA to the ignored
`.runtime/kubernetes` directory (0700 directory, 0600 files). The API container
mounts those files read-only and reaches the fixed local API endpoint through a
certificate-valid hostname. The role permits pod GET/list/watch only; it cannot
create, patch, delete, or read Secrets.

## Fault catalog

The catalog contains three pod actions, two stressors, six network actions,
four HTTP actions, two DNS actions, two I/O actions, and one clock-skew action.
Defaults remain namespace-scoped, bounded to 5–600 seconds, and selected by a
known `app.kubernetes.io/component` label.

Every manifest carries a unique experiment label and must pass both Pydantic
validation and the live Kubernetes admission webhook before validation succeeds.

## Ground-truth isolation

The `experiment_controller` package is a benchmark harness, not part of the
RootLens application. The Dockerfile copies only `src`, so the controller and
its catalog are absent from the runtime image. RootLens's Kubernetes client has
GET/list operations only; mutation is performed by the host's explicit kubectl
context.

Before applying a fault, the controller appends its complete specification and
manifest digest to `events.jsonl`. It records `applied` after Kubernetes accepts
the manifest and `recovered` after cleanup. The directory and journal are forced
to modes 0700 and 0600. The CLI prints only an experiment ID, lifecycle status,
and timestamps—never the fault type or target.

Keep the ground-truth directory on the host, outside any bind mount. The default
is the sibling path `../.rootlens-ground-truth`, which is outside the repository;
a repository-local `.ground-truth` fallback is ignored by Git.

## Safe workflow

```bash
make k8s-up
make chaos-validate
make chaos-smoke
make gateway-smoke
make topology-smoke
```

`make chaos-smoke` is destructive to one disposable checkout pod. It requires
the CLI's explicit confirmation flag, limits the experiment to 10 seconds,
deletes the Chaos resource in a `finally` cleanup path, and then verifies the
hidden lifecycle. Kubernetes recreates the killed pod through its Deployment.

For a catalog preview or manifest rendering without mutation:

```bash
.venv/bin/python -m experiment_controller.cli catalog
.venv/bin/python -m experiment_controller.cli render --fault network_latency --duration 30
```

To remove the disposable cluster while retaining RootLens database and backend
volumes:

```bash
make k8s-down
```

Never mount the ground-truth directory into RootLens, the demo, or telemetry
backends. Doing so would invalidate blind-diagnosis evaluation.
