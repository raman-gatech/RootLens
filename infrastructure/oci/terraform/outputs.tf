output "cluster_id" {
  description = "The OCID of the OKE cluster."
  value       = oci_containerengine_cluster.rootlens_cluster.id
}

output "cluster_name" {
  description = "The name of the OKE cluster."
  value       = oci_containerengine_cluster.rootlens_cluster.name
}

output "kubernetes_endpoint" {
  description = "The endpoint URL for the Kubernetes cluster API."
  value       = oci_containerengine_cluster.rootlens_cluster.endpoints[0].public_endpoint
}

output "kubeconfig_command" {
  description = "OCI CLI command to generate local kubeconfig for the cluster."
  value       = "oci ce cluster create-kubeconfig --cluster-id ${oci_containerengine_cluster.rootlens_cluster.id} --file $HOME/.kube/config --region ${var.region} --token-version 2.0.0 --kube-endpoint PUBLIC_ENDPOINT"
}

output "node_pool_id" {
  description = "The OCID of the Ampere worker node pool."
  value       = oci_containerengine_node_pool.rootlens_ampere_pool.id
}

output "lb_subnet_id" {
  description = "The OCID of the public load balancer subnet."
  value       = oci_core_subnet.lb_subnet.id
}

