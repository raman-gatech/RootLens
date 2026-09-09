variable "tenancy_ocid" {
  type        = string
  description = "The OCID of the root tenancy."
}

variable "user_ocid" {
  type        = string
  description = "The OCID of the user calling the API."
}

variable "compartment_ocid" {
  type        = string
  description = "The OCID of the compartment containing RootLens resources."
}

variable "region" {
  type        = string
  description = "OCI home or targeted region (e.g. us-ashburn-1, us-phoenix-1, us-chicago-1)."
}

variable "fingerprint" {
  type        = string
  description = "The fingerprint of the API signing key."
}

variable "private_key_path" {
  type        = string
  description = "Local path to the OCI API private key (PEM format)."
}

variable "cluster_name" {
  type        = string
  description = "Name for the OKE cluster."
  default     = "rootlens-production"
}

variable "kubernetes_version" {
  type        = string
  description = "Kubernetes version for the OKE cluster control plane and worker nodes."
  default     = "v1.31.1"
}

variable "node_shape" {
  type        = string
  description = "The compute shape for worker nodes. VM.Standard.A1.Flex is Always Free eligible."
  default     = "VM.Standard.A1.Flex"

  validation {
    condition     = var.node_shape == "VM.Standard.A1.Flex"
    error_message = "Only VM.Standard.A1.Flex is permitted to ensure Always Free tier compliance."
  }
}

variable "node_count" {
  type        = number
  description = "Number of worker nodes in the Ampere node pool."
  default     = 2

  validation {
    condition     = var.node_count >= 1 && var.node_count <= 4
    error_message = "Node count must be between 1 and 4 for Always Free Ampere capacity."
  }
}

variable "node_ocpus" {
  type        = number
  description = "OCPUs allocated per worker node."
  default     = 1

  validation {
    condition     = var.node_ocpus >= 1 && var.node_ocpus <= 4
    error_message = "OCPUs per node must be between 1 and 4."
  }
}

variable "node_memory_in_gbs" {
  type        = number
  description = "Memory in GBs allocated per worker node."
  default     = 6

  validation {
    condition     = var.node_memory_in_gbs >= 6 && var.node_memory_in_gbs <= 24
    error_message = "Memory per node must be between 6 GB and 24 GB."
  }
}

variable "admin_source_cidr" {
  type        = string
  description = "Administrator public IP CIDR (/32) allowed to access Kubernetes API and SSH."

  validation {
    condition     = can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}/(?:32|24)$", var.admin_source_cidr))
    error_message = "admin_source_cidr must be a valid IPv4 CIDR (e.g. 203.0.113.10/32)."
  }
}

variable "ssh_public_key" {
  type        = string
  description = "SSH public key for node access (optional)."
  default     = ""
}

