output "instance_id" {
  description = "The EC2 instance ID."
  value       = aws_instance.rootlens_server.id
}

output "public_ip" {
  description = "The static public IP address of the RootLens Free Tier server."
  value       = aws_eip.rootlens_eip.public_ip
}

output "rootlens_web_url" {
  description = "Public URL to access the RootLens Web UI and health probes."
  value       = "http://${aws_eip.rootlens_eip.public_ip}:8000"
}

output "ssh_command" {
  description = "SSH command to connect to the RootLens server."
  value       = "ssh ubuntu@${aws_eip.rootlens_eip.public_ip}"
}

output "kubeconfig_fetch_command" {
  description = "Command to fetch the remote k3s kubeconfig to your local machine."
  value       = "ssh ubuntu@${aws_eip.rootlens_eip.public_ip} 'sudo cat /etc/rancher/k3s/k3s.yaml' | sed 's/127.0.0.1/${aws_eip.rootlens_eip.public_ip}/' > ~/.kube/rootlens-aws-k3s.yaml"
}

