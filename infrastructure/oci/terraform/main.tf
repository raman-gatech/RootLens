terraform {
  required_version = ">= 1.5.0"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 6.0"
    }
  }
}

provider "oci" {
  tenancy_ocid     = var.tenancy_ocid
  user_ocid        = var.user_ocid
  compartment_ocid = var.compartment_ocid
  region           = var.region
  fingerprint      = var.fingerprint
  private_key_path = var.private_key_path
}

# --- Always Free Budget Verification ---
check "always_free_budget_check" {
  assert {
    condition     = (var.node_count * var.node_ocpus) <= 4
    error_message = "Total OCPUs across all nodes (${var.node_count * var.node_ocpus}) exceeds OCI Always Free limit of 4 OCPUs."
  }
  assert {
    condition     = (var.node_count * var.node_memory_in_gbs) <= 24
    error_message = "Total memory across all nodes (${var.node_count * var.node_memory_in_gbs} GB) exceeds OCI Always Free limit of 24 GB RAM."
  }
}

# --- Networking (VCN & Subnets) ---
resource "oci_core_vcn" "rootlens_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.0.0.0/16"]
  display_name   = "rootlens-vcn"
  dns_label      = "rootlens"

  freeform_tags = {
    "Project"     = "RootLens"
    "Environment" = "Production"
  }
}

resource "oci_core_internet_gateway" "rootlens_igw" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.rootlens_vcn.id
  display_name   = "rootlens-igw"
  enabled        = true
}

resource "oci_core_nat_gateway" "rootlens_nat" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.rootlens_vcn.id
  display_name   = "rootlens-nat"
}

resource "oci_core_service_gateway" "rootlens_sgw" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.rootlens_vcn.id
  display_name   = "rootlens-sgw"

  services {
    service_id = data.oci_core_services.all_services.services[0].id
  }
}

data "oci_core_services" "all_services" {}

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.compartment_ocid
}

# --- Route Tables ---
resource "oci_core_route_table" "public_rt" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.rootlens_vcn.id
  display_name   = "rootlens-public-rt"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.rootlens_igw.id
  }
}

resource "oci_core_route_table" "private_rt" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.rootlens_vcn.id
  display_name   = "rootlens-private-rt"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_nat_gateway.rootlens_nat.id
  }
  route_rules {
    destination       = data.oci_core_services.all_services.services[0].cidr_block
    destination_type  = "SERVICE_CIDR_BLOCK"
    network_entity_id = oci_core_service_gateway.rootlens_sgw.id
  }
}

# --- Security Lists ---
resource "oci_core_security_list" "k8s_api_endpoint_sl" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.rootlens_vcn.id
  display_name   = "rootlens-k8s-api-sl"

  ingress_security_rules {
    protocol    = "6" # TCP
    source      = var.admin_source_cidr
    source_type = "CIDR_BLOCK"
    tcp_options {
      min = 6443
      max = 6443
    }
  }

  ingress_security_rules {
    protocol    = "6" # TCP
    source      = "10.0.10.0/24" # Worker nodes subnet
    source_type = "CIDR_BLOCK"
    tcp_options {
      min = 6443
      max = 6443
    }
  }

  egress_security_rules {
    protocol         = "6" # TCP
    destination      = "10.0.10.0/24"
    destination_type = "CIDR_BLOCK"
  }
}

resource "oci_core_security_list" "workers_sl" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.rootlens_vcn.id
  display_name   = "rootlens-workers-sl"

  ingress_security_rules {
    protocol    = "all"
    source      = "10.0.10.0/24"
    source_type = "CIDR_BLOCK"
  }

  ingress_security_rules {
    protocol    = "6" # TCP
    source      = "10.0.20.0/24" # Public LB subnet
    source_type = "CIDR_BLOCK"
  }

  egress_security_rules {
    protocol         = "all"
    destination      = "0.0.0.0/0"
    destination_type = "CIDR_BLOCK"
  }
}

resource "oci_core_security_list" "lb_sl" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.rootlens_vcn.id
  display_name   = "rootlens-lb-sl"

  ingress_security_rules {
    protocol    = "6" # TCP
    source      = "0.0.0.0/0"
    source_type = "CIDR_BLOCK"
    tcp_options {
      min = 80
      max = 80
    }
  }

  ingress_security_rules {
    protocol    = "6" # TCP
    source      = "0.0.0.0/0"
    source_type = "CIDR_BLOCK"
    tcp_options {
      min = 443
      max = 443
    }
  }

  egress_security_rules {
    protocol         = "6" # TCP
    destination      = "10.0.10.0/24"
    destination_type = "CIDR_BLOCK"
  }
}

# --- Subnets ---
resource "oci_core_subnet" "k8s_api_subnet" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.rootlens_vcn.id
  cidr_block                 = "10.0.0.0/28"
  display_name               = "rootlens-k8s-api-subnet"
  route_table_id             = oci_core_route_table.public_rt.id
  security_list_ids          = [oci_core_security_list.k8s_api_endpoint_sl.id]
  prohibit_public_ip_on_vnic = false
}

resource "oci_core_subnet" "workers_subnet" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.rootlens_vcn.id
  cidr_block                 = "10.0.10.0/24"
  display_name               = "rootlens-workers-subnet"
  route_table_id             = oci_core_route_table.private_rt.id
  security_list_ids          = [oci_core_security_list.workers_sl.id]
  prohibit_public_ip_on_vnic = true
}

resource "oci_core_subnet" "lb_subnet" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.rootlens_vcn.id
  cidr_block                 = "10.0.20.0/24"
  display_name               = "rootlens-lb-subnet"
  route_table_id             = oci_core_route_table.public_rt.id
  security_list_ids          = [oci_core_security_list.lb_sl.id]
  prohibit_public_ip_on_vnic = false
}

# --- OKE Kubernetes Cluster ---
resource "oci_containerengine_cluster" "rootlens_cluster" {
  compartment_id     = var.compartment_ocid
  name               = var.cluster_name
  kubernetes_version = var.kubernetes_version
  vcn_id             = oci_core_vcn.rootlens_vcn.id

  endpoint_config {
    is_public_ip_enabled = true
    subnet_id            = oci_core_subnet.k8s_api_subnet.id
    nsg_ids              = []
  }

  options {
    service_lb_subnet_ids = [oci_core_subnet.lb_subnet.id]
    add_ons {
      is_kubernetes_dashboard_enabled = false
      is_tiller_enabled               = false
    }
    admission_controller_options {
      is_pod_security_policy_enabled = false
    }
  }

  type = "BASIC_CLUSTER" # Free-tier supported
}

# --- Ampere A1 Compute Node Pool ---
resource "oci_containerengine_node_pool" "rootlens_ampere_pool" {
  cluster_id         = oci_containerengine_cluster.rootlens_cluster.id
  compartment_id     = var.compartment_ocid
  kubernetes_version = var.kubernetes_version
  name               = "rootlens-ampere-pool"
  node_shape         = var.node_shape

  node_shape_config {
    ocpus         = var.node_ocpus
    memory_in_gbs = var.node_memory_in_gbs
  }

  node_source_details {
    image_id    = data.oci_core_images.oracle_linux_arm.images[0].id
    source_type = "IMAGE"
  }

  node_config_details {
    size = var.node_count

    placement_configs {
      availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
      subnet_id           = oci_core_subnet.workers_subnet.id
    }
  }

  ssh_public_key = var.ssh_public_key != "" ? var.ssh_public_key : null
}

data "oci_core_images" "oracle_linux_arm" {
  compartment_id           = var.compartment_ocid
  operating_system         = "Oracle Linux"
  operating_system_version = "8"
  shape                    = "VM.Standard.A1.Flex"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

