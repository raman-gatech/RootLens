# AWS Free Tier Deployment & Demo Proof Guide

This guide details the complete process for provisioning, configuring, and verifying RootLens on Amazon Web Services (AWS) using the **AWS 12-Month Free Tier**.

---

## 1. Architecture: 100% Free Tier Compliant

Unlike AWS EKS (which charges a mandatory \$0.10/hr / ~\$73/month control plane fee), RootLens on AWS Free Tier uses an optimized single-node architecture:
- **Compute**: `t3.micro` or `t2.micro` (750 hours/month free under the AWS 12-Month Free Tier).
- **Storage**: 30 GB `gp3` General Purpose SSD root volume (30 GB/month free EBS limit).
- **Kubernetes**: Lightweight production Kubernetes (`k3s`) installed directly via `cloud-init`, with zero control-plane fee.
- **Networking**: VPC with public subnet, Internet Gateway, and an Elastic IP (free while attached to a running instance).
- **Ingress / Web Access**: Port 80, 443, and 8000 directly exposed through the AWS Security Group.

```
                      +-----------------------------+
                      |       Public Internet       |
                      +--------------+--------------+
                                     |
                          +----------v----------+
                          |   AWS Elastic IP    |
                          |  (Port 80 / 8000)   |
                          +----------+----------+
                                     |
            +------------------------+------------------------+
            |                        VPC                      |
            |   +-----------------------------------------+   |
            |   |           EC2 t3.micro Instance         |   |
            |   |               (30 GB gp3)               |   |
            |   |   +---------------------------------+   |   |
            |   |   |        k3s Kubernetes Node      |   |   |
            |   |   |  - rootlens-api                 |   |   |
            |   |   |  - postgres-db (pgvector)       |   |   |
            |   |   |  - otel-collector               |   |   |
            |   |   |  - prometheus / tempo / loki    |   |   |
            |   |   +---------------------------------+   |   |
            |   +-----------------------------------------+   |
            +-------------------------------------------------+
```

---

## 2. Prerequisites & Credentials

1. **AWS Account** with active 12-month Free Tier.
2. **AWS CLI** installed and configured:
   ```bash
   aws configure
   # Enter AWS Access Key ID, Secret Access Key, and Default Region (e.g., us-east-1)
   ```
3. Or export environment variables directly:
   ```bash
   export AWS_ACCESS_KEY_ID="AKIA..."
   export AWS_SECRET_ACCESS_KEY="..."
   export AWS_DEFAULT_REGION="us-east-1"
   ```

---

## 3. Terraform Provisioning

1. Navigate to the AWS Terraform directory:
   ```bash
   cd infrastructure/aws/terraform
   ```

2. Initialize and validate the configuration:
   ```bash
   terraform init
   terraform validate
   ```

3. Review the execution plan:
   ```bash
   terraform plan -out=tfplan
   ```

4. Apply the plan to provision the server:
   ```bash
   terraform apply tfplan
   ```

5. Retrieve deployment outputs:
   ```bash
   terraform output
   # Returns:
   # - public_ip
   # - rootlens_web_url
   # - ssh_command
   # - kubeconfig_fetch_command
   ```

---

## 4. Deployment Verification & Demo Proof

Once the instance is online, run the following automated verification checks:

1. **Verify SSH & k3s Cluster Health**:
   ```bash
   # Connect to the instance
   ssh ubuntu@<PUBLIC_IP>

   # Verify k3s nodes and system pods
   kubectl get nodes
   kubectl get pods -A
   ```

2. **Verify RootLens Web UI & Live Probes**:
   ```bash
   # Health check live probe (HTTP 200)
   curl -i http://<PUBLIC_IP>:8000/health/live

   # Health check readiness probe (HTTP 200)
   curl -i http://<PUBLIC_IP>:8000/health/ready
   ```

3. **Browser Demo**:
   Open your browser and navigate to:
   ```
   http://<PUBLIC_IP>:8000
   ```
   - Log in with operator credentials.
   - Inspect the interactive service topology graph.
   - Create an incident, trigger multi-agent investigation, and verify real-time causal diagnosis.

---

## 5. Teardown / Destroy

When finished demonstrating the deployment proof:
```bash
cd infrastructure/aws/terraform
terraform destroy -auto-approve
```
