locals {
  always_free = jsondecode(file("${path.module}/../free-tier-budget.json"))
  tags = {
    application  = "rootlens"
    environment  = "production"
    managed-by   = "terraform"
    cost-profile = "oci-always-free"
  }
}

check "always_free_compute_budget" {
  assert {
    condition = (
      var.worker_count * var.worker_ocpus <= local.always_free.compute.ocpus &&
      var.worker_count * var.worker_memory_gb <= local.always_free.compute.memory_gb
    )
    error_message = "Worker allocation exceeds the encoded OCI Always Free compute budget."
  }
}

check "always_free_boot_volume_budget" {
  assert {
    condition = (
      var.worker_count * var.worker_boot_volume_gb <=
      local.always_free.storage.total_boot_and_block_gb
    )
    error_message = "Worker boot volumes exceed the encoded OCI Always Free storage budget."
  }
}

module "oke" {
  source  = "oracle-terraform-modules/oke/oci"
  version = "5.5.1"

  providers = {
    oci      = oci
    oci.home = oci.home
  }

  tenancy_id     = var.tenancy_ocid
  compartment_id = var.compartment_ocid
  region         = var.region

  create_iam_resources     = true
  create_iam_tag_namespace = false
  create_iam_defined_tags  = false
  use_defined_tags         = false

  create_vcn                  = true
  vcn_name                    = "rootlens-production"
  vcn_dns_label               = "rootlens"
  vcn_cidrs                   = ["10.42.0.0/16"]
  vcn_create_internet_gateway = "always"
  vcn_create_nat_gateway      = "never"
  vcn_create_service_gateway  = "always"
  lockdown_default_seclist    = true

  subnets = {
    bastion  = { create = "never" }
    operator = { create = "never" }
    cp       = { create = "always", newbits = 8 }
    int_lb   = { create = "never" }
    pub_lb   = { create = "always", newbits = 8 }
    workers  = { create = "always", newbits = 8 }
    pods     = { create = "never" }
  }

  nsgs = {
    bastion  = { create = "never" }
    operator = { create = "never" }
    cp       = { create = "always" }
    int_lb   = { create = "never" }
    pub_lb   = { create = "always" }
    workers  = { create = "always" }
    pods     = { create = "never" }
  }

  control_plane_is_public           = true
  assign_public_ip_to_control_plane = true
  control_plane_allowed_cidrs       = var.control_plane_allowed_cidrs
  worker_is_public                  = true
  allow_worker_internet_access      = true
  allow_pod_internet_access         = true
  allow_worker_ssh_access           = false
  allow_node_port_access            = false
  allow_rules_public_lb             = true
  load_balancers                    = "public"
  preferred_load_balancer           = "public"

  create_bastion  = false
  create_operator = false

  create_cluster     = true
  cluster_name       = var.cluster_name
  cluster_type       = "basic"
  cni_type           = "flannel"
  kubernetes_version = var.kubernetes_version
  output_detail      = false

  ssh_public_key_path                   = var.ssh_public_key_path
  worker_pool_mode                      = "node-pool"
  worker_pool_size                      = var.worker_count
  worker_legacy_imds_endpoints_disabled = true
  worker_shape = {
    shape            = "VM.Standard.A1.Flex"
    ocpus            = var.worker_ocpus
    memory           = var.worker_memory_gb
    boot_volume_size = var.worker_boot_volume_gb
  }
  worker_pools = {
    rootlens = {
      size = var.worker_count
    }
  }

  metrics_server_install = true

  freeform_tags = {
    vcn               = local.tags
    cluster           = local.tags
    workers           = local.tags
    persistent_volume = local.tags
    service_lb        = local.tags
  }
}
