# OCI Always Free production foundation

RootLens uses an OCI Kubernetes Engine (OKE) Basic cluster because it preserves
the existing Kubernetes production contract while keeping the managed control
plane outside the worker compute allowance. Terraform is pinned to Oracle's OKE
module `5.5.1` and the OCI provider `8.19.x`.

The current conservative Always Free profile, verified against Oracle's service
documentation on 2026-09-02, is:

- two `VM.Standard.A1.Flex` workers at 1 OCPU and 6 GB each;
- 100 GB of worker boot volumes from the 200 GB combined boot/block allowance;
- one public flexible load balancer fixed at 10 Mbps;
- no NAT gateway, bastion VM, operator VM, enhanced-cluster fee, or virtual nodes;
- a public Kubernetes endpoint restricted to explicitly supplied administrator
  CIDRs, with public worker addresses used only for outbound image/API access.

This profile is suitable for a public portfolio deployment and acceptance
testing. It is not multi-region or infrastructure-level highly available: both
worker nodes share the tenancy's home region and the total compute capacity is
fixed. The application still runs two replicas, but a regional outage or Always
Free capacity loss requires recovery from backup. A paid production service
should move workers to private subnets behind a NAT gateway, use at least three
failure-domain-distributed nodes, and use a managed PostgreSQL service.

## Required local inputs

1. Create an OCI API signing key and configure it in `~/.oci/config`. Do not put
   the private key, fingerprint, or user OCID in this repository.
2. Copy `infrastructure/oci/terraform/terraform.tfvars.example` to the ignored
   `terraform.tfvars` and set the tenancy OCID, compartment OCID, tenancy home
   region, public SSH key path, and your current public IP as a `/32` control
   plane CIDR.
3. Confirm that Limits, Quotas and Usage shows the required Ampere, block-volume,
   OKE Basic-cluster, and load-balancer capacity in the home region. Always Free
   A1 host capacity can be temporarily unavailable even when the quota exists.

Run the non-mutating validation before provisioning:

```bash
make oci-validate
terraform -chdir=infrastructure/oci/terraform plan -out=rootlens.tfplan
terraform -chdir=infrastructure/oci/terraform show rootlens.tfplan
```

Only apply a reviewed plan that contains the Basic cluster, two A1 workers, one
VCN, no NAT gateway, and no resources outside the home region:

```bash
terraform -chdir=infrastructure/oci/terraform apply rootlens.tfplan
terraform -chdir=infrastructure/oci/terraform output -raw kubeconfig_command
```

Run the emitted OCI CLI command, then store the resulting kubeconfig as the
protected `PRODUCTION_KUBECONFIG` GitHub environment secret. Terraform state
contains resource identifiers and must be stored in an access-controlled,
encrypted backend before team operation; it is ignored locally and must never be
committed.

The next deployment phase installs an NGINX ingress Service annotated as an OCI
flexible load balancer with both the minimum and maximum fixed to `10`, provisions
private telemetry and PostgreSQL endpoints, delegates DNS, and dispatches the
existing protected production workflow.
