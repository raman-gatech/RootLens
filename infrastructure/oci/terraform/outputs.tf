output "cluster_id" {
  description = "OKE cluster OCID used to generate the deployment kubeconfig."
  value       = module.oke.cluster_id
}

output "cluster_endpoints" {
  description = "Public and private OKE control-plane endpoints."
  value       = module.oke.cluster_endpoints
}

output "worker_pool_ids" {
  description = "Managed Ampere worker-pool OCIDs."
  value       = module.oke.worker_pool_ids
}

output "kubeconfig_command" {
  description = "Command that writes a short-lived OCI-authenticated kubeconfig."
  value = format(
    "oci ce cluster create-kubeconfig --cluster-id %s --file ~/.kube/rootlens-oci --region %s --token-version 2.0.0 --kube-endpoint PUBLIC_ENDPOINT",
    module.oke.cluster_id,
    var.region,
  )
}

output "always_free_allocation" {
  description = "Requested resources compared with the encoded Always Free ceiling."
  value = {
    workers       = var.worker_count
    total_ocpus   = var.worker_count * var.worker_ocpus
    total_memory  = var.worker_count * var.worker_memory_gb
    boot_volume   = var.worker_count * var.worker_boot_volume_gb
    load_balancer = "flexible 10 Mbps; configured during ingress installation"
  }
}
