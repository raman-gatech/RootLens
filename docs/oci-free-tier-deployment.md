# OCI Always Free OKE Production Deployment Guide

This guide details the complete process for provisioning, configuring, and verifying RootLens on Oracle Cloud Infrastructure (OCI) using the **Always Free** tier.

---

## 1. OCI Always Free Architecture & Capacity Limits

OCI provides generous Always Free tier resources for Arm-based Ampere compute:

- **Compute**: Up to 4 OCPUs and 24 GB RAM across Ampere A1 (`VM.Standard.A1.Flex`) instances.
- **RootLens Allocation**: **2 worker nodes**, each configured with **1 OCPU and 6 GB RAM** (total 2 OCPUs, 12 GB RAM), leaving remaining quota safely headroom-isolated.
- **Networking**: Flexible Load Balancer pinned to **10 Mbps** (Always Free limit).
- **Cluster**: OKE Basic Cluster (zero cluster management fee).

```
                      +-----------------------------+
                      |       Public Internet       |
                      +--------------+--------------+
                                     |
                          +----------v----------+
                          |   OCI Load Balancer | (10 Mbps Always Free)
                          |    (TCP 80 / 443)   |
                          +----------+----------+
                                     |
            +------------------------+------------------------+
            |                  Private VCN                    |
            |   +-----------------------------------------+   |
            |   |               OKE Cluster               |   |
            |   |                                         |   |
            |   |   +-----------------+ +---------------+ |   |
            |   |   |  Node 1 (Arm64) | | Node 2(Arm64) | |   |
            |   |   |   1 OCPU / 6GB  | |  1 OCPU / 6GB | |   |
            |   |   +-----------------+ +---------------+ |   |
            |   +-----------------------------------------+   |
            +-------------------------------------------------+
```

---

## 2. Prerequisites

1. **OCI Account** with active Always Free Ampere capacity in your home region.
2. **OCI CLI & API Signing Key**:
   - Private key generated (`~/.oci/oci_api_key.pem`).
   - Fingerprint uploaded to OCI Console under User Profile -> API Keys.
3. **Required Identifiers**:
   - `tenancy_ocid`
   - `user_ocid`
   - `compartment_ocid`
   - `region` (e.g. `us-ashburn-1`, `us-phoenix-1`)
   - `admin_source_cidr` (Your public IP, e.g. `203.0.113.10/32`)

---

## 3. Terraform Provisioning

1. Navigate to the Terraform directory:

   ```bash
   cd infrastructure/oci/terraform
   ```

2. Create `terraform.tfvars`:

   ```hcl
   tenancy_ocid      = "ocid1.tenancy.oc1..aaaa..."
   user_ocid         = "ocid1.user.oc1..aaaa..."
   compartment_ocid  = "ocid1.compartment.oc1..aaaa..."
   region            = "us-ashburn-1"
   fingerprint       = "xx:xx:xx:..."
   private_key_path  = "~/.oci/oci_api_key.pem"
   admin_source_cidr = "YOUR_PUBLIC_IP/32"
   node_count        = 2
   node_ocpus        = 1
   node_memory_in_gbs = 6
   ```

3. Initialize and validate:

   ```bash
   terraform init
   terraform validate
   ```

4. Plan and apply:

   ```bash
   terraform plan -out=tfplan
   terraform apply tfplan
   ```

5. Retrieve Kubeconfig:
   ```bash
   $(terraform output -raw kubeconfig_command)
   kubectl get nodes
   ```

---

## 4. Ingress & cert-manager Installation

1. Install NGINX Ingress Controller:

   ```bash
   helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
   helm repo update
   helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
     --namespace ingress-nginx --create-namespace \
     --set controller.service.annotations."service\.beta\.kubernetes\.io/oci-load-balancer-shape"="flexible" \
     --set controller.service.annotations."service\.beta\.kubernetes\.io/oci-load-balancer-shape-flex-min"="10" \
     --set controller.service.annotations."service\.beta\.kubernetes\.io/oci-load-balancer-shape-flex-max"="10"
   ```

2. Install cert-manager:

   ```bash
   helm repo add jetstack https://charts.jetstack.io
   helm repo update
   helm upgrade --install cert-manager jetstack/cert-manager \
     --namespace cert-manager --create-namespace \
     --set crds.enabled=true
   ```

3. Deploy ClusterIssuer:
   ```bash
   kubectl apply -f deploy/production/cert-manager-issuer.yaml
   ```

---

## 5. Secret Provisioning & Phased Manifest Deployment

1. Create application namespace:

   ```bash
   kubectl create namespace rootlens-system
   ```

2. Create runtime secrets:

   ```bash
   kubectl create secret generic rootlens-runtime \
     --namespace rootlens-system \
     --from-literal=database-url="postgresql+asyncpg://admin:SECRET@db.internal:5432/rootlens" \
     --from-literal=openai-api-key="sk-proj-..."

   kubectl create secret generic rootlens-auth \
     --namespace rootlens-system \
     --from-file=credentials.json=/path/to/credentials.json
   ```

3. Render phased manifests:

   ```bash
   python scripts/render_production.py \
     --output-directory .runtime/rendered \
     --hostname rootlens.yourdomain.com \
     --image ghcr.io/raman-gatech/rootlens@sha256:<IMMUTABLE_DIGEST> \
     --ingress-class nginx \
     --monitored-namespace default \
     --otlp-endpoint http://otel-collector.observability.svc:4317 \
     --prometheus-url http://prometheus.observability.svc:9090 \
     --tempo-url http://tempo.observability.svc:3200 \
     --loki-url http://loki.observability.svc:3100
   ```

4. Apply phased manifests:
   ```bash
   kubectl apply -f .runtime/rendered/01-prerequisites.yaml
   kubectl apply -f .runtime/rendered/02-migration.yaml
   kubectl wait --for=condition=complete --timeout=120s job/rootlens-migrate -n rootlens-system
   kubectl apply -f .runtime/rendered/03-application.yaml
   kubectl apply -f .runtime/rendered/04-ingress.yaml
   ```

---

## 6. Verification, Smoke Testing & Rollback

1. **Verify Pod Status & Endpoints**:

   ```bash
   kubectl get pods -n rootlens-system
   curl -fk https://rootlens.yourdomain.com/health/live
   curl -fk https://rootlens.yourdomain.com/health/ready
   ```

2. **Rollback Procedure**:
   If a deployment failure or regression occurs:
   ```bash
   kubectl rollout undo deployment/rootlens-api -n rootlens-system
   kubectl rollout status deployment/rootlens-api -n rootlens-system
   ```
