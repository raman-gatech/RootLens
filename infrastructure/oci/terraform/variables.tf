variable "tenancy_ocid" {
  description = "OCI tenancy OCID."
  type        = string

  validation {
    condition     = startswith(var.tenancy_ocid, "ocid1.tenancy.")
    error_message = "tenancy_ocid must be an OCI tenancy OCID."
  }
}

variable "compartment_ocid" {
  description = "OCI compartment OCID in the tenancy home region."
  type        = string

  validation {
    condition     = startswith(var.compartment_ocid, "ocid1.compartment.")
    error_message = "compartment_ocid must be an OCI compartment OCID."
  }
}

variable "region" {
  description = "OCI tenancy home region; Always Free resources must be created here."
  type        = string

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]+$", var.region))
    error_message = "region must be an OCI region name such as us-ashburn-1."
  }
}

variable "oci_profile" {
  description = "Profile in ~/.oci/config; credentials never belong in tfvars or state."
  type        = string
  default     = "DEFAULT"
}

variable "ssh_public_key_path" {
  description = "Path to the public SSH key placed on managed worker nodes."
  type        = string
}

variable "control_plane_allowed_cidrs" {
  description = "Trusted public IPv4 CIDRs allowed to reach the Kubernetes API."
  type        = list(string)

  validation {
    condition = length(var.control_plane_allowed_cidrs) > 0 && alltrue([
      for cidr in var.control_plane_allowed_cidrs :
      can(cidrhost(cidr, 0)) && cidr != "0.0.0.0/0"
    ])
    error_message = "Provide at least one valid restricted CIDR; 0.0.0.0/0 is forbidden."
  }
}

variable "cluster_name" {
  description = "OKE cluster display name."
  type        = string
  default     = "rootlens-production"
}

variable "kubernetes_version" {
  description = "OKE-supported Kubernetes version in the selected home region."
  type        = string
  default     = "v1.34.2"

  validation {
    condition     = can(regex("^v1\\.[0-9]+\\.[0-9]+$", var.kubernetes_version))
    error_message = "kubernetes_version must look like v1.34.2."
  }
}

variable "worker_count" {
  description = "Number of Always Free Ampere workers."
  type        = number
  default     = 2

  validation {
    condition     = var.worker_count >= 1 && var.worker_count <= 2
    error_message = "The RootLens Always Free profile supports one or two workers."
  }
}

variable "worker_ocpus" {
  description = "OCPUs assigned to each Ampere worker."
  type        = number
  default     = 1

  validation {
    condition     = var.worker_ocpus >= 1
    error_message = "Each managed OKE worker requires at least one OCPU."
  }
}

variable "worker_memory_gb" {
  description = "Memory assigned to each Ampere worker in GB."
  type        = number
  default     = 6

  validation {
    condition     = var.worker_memory_gb >= 6
    error_message = "Each RootLens worker requires at least 6 GB of memory."
  }
}

variable "worker_boot_volume_gb" {
  description = "Boot volume size for each worker; OCI managed nodes require at least 50 GB."
  type        = number
  default     = 50

  validation {
    condition     = var.worker_boot_volume_gb == 50
    error_message = "Keep each worker boot volume at the 50 GB Always Free minimum."
  }
}
