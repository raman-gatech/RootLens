# Local development

## Commands

```bash
make bootstrap       # create .venv and install development dependencies
make check           # formatting, linting, typing, tests, Compose validation
make up              # start and verify the full local stack
make smoke           # rerun live stack verification
make gateway-smoke   # query live backends through Milestone 2 clients
make topology-smoke  # reconstruct, persist, and traverse a live service graph
make k8s-up           # run the demo in kind with Chaos Mesh
make k8s-smoke        # verify cluster, workloads, frontend, and all fault CRDs
make chaos-validate   # server-side dry-run all five fault manifests
make chaos-smoke      # inject a 10-second pod kill and verify hidden truth
make k8s-down         # delete only the kind cluster
make migrate         # apply database migrations
make down            # stop containers without deleting volumes
```

Run `make format` before committing code. The CI workflow runs `make check` on
Python 3.12 and checks out the OpenTelemetry Demo submodule recursively. The
Kubernetes scripts install pinned kind and Helm binaries under `.tools/`; they
do not modify a system-wide package manager.

## Environment boundary

`.env.compose` contains non-secret local defaults. Put host-only overrides in an
untracked `.env`; the Python settings loader reads variables with the
`ROOTLENS_` prefix. Do not add production credentials to either tracked file.

The OpenTelemetry Demo uses its pinned `vendor/opentelemetry-demo/.env`, with
RootLens overrides applied from `.env.compose`.

The experiment controller writes full fault ground truth outside the repository
at `../.rootlens-ground-truth` by default. Override `GROUND_TRUTH_DIR` only with
a host path that is unavailable to RootLens containers and Kubernetes workloads.
See the [fault-injection runbook](fault-injection.md) before running experiments.

## Common problems

If containers are repeatedly killed, increase Docker Desktop's memory allocation
to at least 8 GB for the Kubernetes mode. The demo contains multiple polyglot
services.

If port 5433, 8000, 8080, 9090, 3100, 3200, 4317, 4318, or 3001 is already in
use, stop the conflicting local service before running `make up`.
Kubernetes mode exposes the demo on port 18080 instead of 8080.

Telemetry is asynchronous. `make up` allows up to three minutes for each live
verification check, including Tempo service-graph generation.

To inspect failures:

```bash
ROOTLENS_PROJECT_DIR="$PWD" docker compose \
  --project-name rootlens \
  --env-file vendor/opentelemetry-demo/.env \
  --env-file .env.compose \
  -f vendor/opentelemetry-demo/compose.yaml \
  -f compose.yaml ps
```

Use the same prefix with `logs <service-name>` to inspect a specific container.
