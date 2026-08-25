# Security policy

## Supported versions

Security fixes are applied to the latest release on `main`. RootLens 1.x is the
currently supported release line.

## Reporting a vulnerability

Do not open a public issue containing exploit details, credentials, or private
telemetry. Use GitHub's **Security → Report a vulnerability** workflow for this
repository. Include the affected version, impact, reproduction steps, and any
suggested mitigation. Maintainers should acknowledge a report within five
business days and coordinate disclosure after a fix is available.

## Deployment boundary

The default Compose environment is a localhost development and chaos-testing
stack. It is not an internet-facing deployment. Production deployments must:

- enable bearer authentication and use individual principals with least-privilege
  permissions;
- terminate TLS at a trusted ingress or load balancer;
- keep PostgreSQL and telemetry backends on private networks;
- mount credentials from a secret manager rather than source control;
- keep remediation execution disabled unless a separately reviewed operator
  identity and Kubernetes mutation policy are installed;
- pin the runtime image by digest and apply migrations as an explicit release step.

See [Production deployment](docs/production-deployment.md) for the complete
checklist.
