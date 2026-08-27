# Production deployment

The default Compose stack is deliberately optimized for localhost development
and chaos testing. Production uses the templates in `deploy/production`, an
external PostgreSQL/pgvector service, private telemetry backends, a TLS ingress,
and secrets supplied by the deployment platform.

## Protected deployment workflow

`Production Deployment` is the supported promotion path. It targets the GitHub
environment named `production`, refuses example/localhost inputs, requires the
immutable RootLens GHCR digest, and renders manifests into four ordered phases:
prerequisites, migration, application, and ingress. The migration Job must
complete before the two-replica application rollout starts. The workflow then
proves the deployed digest, public DNS, publicly trusted TLS, readiness, HSTS,
anonymous rejection, and authenticated read access.

Configure these non-secret `production` environment variables:

| Variable | Meaning |
| --- | --- |
| `ROOTLENS_HOSTNAME` | Public DNS name already delegated to the ingress load balancer |
| `ROOTLENS_INGRESS_CLASS` | NGINX-compatible Kubernetes ingress class |
| `ROOTLENS_INGRESS_NAMESPACE` | Namespace containing the ingress controller |
| `ROOTLENS_KUBE_CONTEXT` | Context name inside the supplied kubeconfig |
| `ROOTLENS_MONITORED_NAMESPACE` | Workload namespace RootLens may observe |
| `ROOTLENS_OTLP_ENDPOINT` | Private OTLP HTTP(S) endpoint |
| `ROOTLENS_PROMETHEUS_URL` | Private Prometheus HTTP(S) endpoint |
| `ROOTLENS_TEMPO_URL` | Private Tempo HTTP(S) endpoint |
| `ROOTLENS_LOKI_URL` | Private Loki HTTP(S) endpoint |

Configure these `production` environment secrets:

| Secret | Requirement |
| --- | --- |
| `PRODUCTION_KUBECONFIG` | Least-privilege deployment kubeconfig |
| `ROOTLENS_DATABASE_URL` | `postgresql+asyncpg` URL with certificate/hostname verification via `ssl=verify-full` |
| `ROOTLENS_AUTH_CREDENTIALS` | Complete digest-only credentials JSON document |
| `ROOTLENS_SMOKE_TOKEN` | Raw token matching a credential with `read` permission |
| `OPENAI_API_KEY` | OpenAI key for production investigations and the real-model study |
| `ROOTLENS_TLS_CERTIFICATE` | Public certificate/full chain valid for `ROOTLENS_HOSTNAME` |
| `ROOTLENS_TLS_PRIVATE_KEY` | Matching private key |

Protect the environment with required reviewers and restrict its deployment
branches to `main`. Secrets are materialized as mode-0600 runner files, applied
to Kubernetes without appearing on command lines, and removed unconditionally.
The workflow uses the dedicated `rootlens-production` server-side field manager
and claims conflicts only on the RootLens resources declared in these manifests.
The RootLens service account receives a namespaced Role in only
`ROOTLENS_MONITORED_NAMESPACE`; it has no cluster-wide workload read access.
Promotion also removes the legacy `rootlens-production-reader` ClusterRole and
ClusterRoleBinding if they exist.
Dispatch with confirmation `deploy-production`; retain the default v1.0.1 digest
unless promoting a separately signed release. DNS and the ingress controller/load
balancer must exist before dispatch. The included ingress enforces HTTPS,
request-size limits, and NGINX connection/request rate limits.

## Release checklist

1. Build the image from a reviewed commit and sign it in your registry. Replace
   the template image tag with its immutable digest.
2. Back up PostgreSQL, run `migrate-job.yaml`, and require it to complete before
   rolling out the Deployment. `/health/ready` rejects the wrong schema revision.
   A database administrator must install the `vector` extension in the target
   database once; schema migrations then run as the least-privilege application
   role.
3. Configure the protected workflow variables. The renderer replaces every
   example hostname/backend and the workflow labels only the selected ingress
   namespace with `rootlens.io/api-access=true`.
4. Create `rootlens-runtime` with `database-url` and, only when selected,
   `openai-api-key`. Use a TLS-enabled PostgreSQL URL with a dedicated,
   least-privilege database role.
5. Create `rootlens-auth` from a credentials document. Never commit raw tokens or
   token digests. Issue a separate token per human or integration and grant only
   the required permissions: `read`, `investigate`, `ingest`, `publish`, or
   `remediate`.
6. Keep remediation execution disabled initially. The production service account
   is read-only and cannot restart pods. Any future mutation identity requires a
   separate threat model, change review, and namespace allowlist.
7. Configure TLS, request-size limits, and per-principal rate limits at the
   ingress. Forward proxy headers only from the trusted sidecar or ingress.
8. Export application logs and OTLP signals, alert on readiness failures, elevated
   5xx rates, investigation failures, exhausted budgets, and remediation-policy
   rejections.

## Authentication file

RootLens stores only SHA-256 token digests. Generate at least 32 random bytes per
principal and put the digest—not the raw token—in `credentials.json`:

```json
{
  "credentials": [
    {
      "principal": "oncall@example.com",
      "token_sha256": "<64 lowercase hexadecimal characters>",
      "permissions": ["read", "investigate", "remediate"]
    },
    {
      "principal": "prometheus",
      "token_sha256": "<different 64-character digest>",
      "permissions": ["ingest"]
    }
  ]
}
```

Create the secrets without placing values on a command line recorded in shell
history:

```bash
kubectl --namespace rootlens-system create secret generic rootlens-auth \
  --from-file=credentials.json=/secure/path/credentials.json
kubectl --namespace rootlens-system create secret generic rootlens-runtime \
  --from-file=database-url=/secure/path/database-url
```

The file must not be group/world writable. The API compares token digests in
constant time, binds remediation audit identity to the authenticated principal,
and returns only generic 401/403 errors.

## Availability and rollback

The template starts two replicas, uses rolling updates, topology spreading, a
PodDisruptionBudget, resource bounds, startup/liveness/readiness probes, and CPU
autoscaling. Database migrations are forward release steps. Roll back application
pods only to a version compatible with the migrated schema; restore a tested
database backup rather than casually running destructive downgrade migrations.

The local deterministic provider is suitable for reproducible operation without
external model availability. When the OpenAI provider is selected, startup fails
unless a key is present; configure provider timeouts and investigate model/cost
alerts before enabling it for on-call workflows.

For a local production-acceptance test, `kind-tls-ingress.yaml` provides a
non-root, read-only TLS edge at `rootlens.localhost`. Its certificate must be
supplied as the `rootlens-tls` Secret. This acceptance edge is not a replacement
for public DNS, a publicly trusted certificate, or the managed ingress used by a
real production cluster.
