provider "oci" {
  config_file_profile = var.oci_profile
  region              = var.region
}

provider "oci" {
  alias               = "home"
  config_file_profile = var.oci_profile
  region              = var.region
}
