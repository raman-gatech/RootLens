variable "aws_region" {
  type        = string
  description = "AWS target region (e.g., us-east-1, us-west-2, eu-central-1)."
  default     = "us-east-1"
}

variable "instance_type" {
  type        = string
  description = "EC2 instance type eligible for AWS Free Tier."
  default     = "t3.micro"

  validation {
    condition     = contains(["t2.micro", "t3.micro", "t4g.small"], var.instance_type)
    error_message = "Only t2.micro, t3.micro, or t4g.small are eligible for AWS Free Tier compute."
  }
}

variable "root_volume_size_gb" {
  type        = number
  description = "Root EBS storage size in GB (Free Tier allows up to 30 GB EBS)."
  default     = 30

  validation {
    condition     = var.root_volume_size_gb >= 20 && var.root_volume_size_gb <= 30
    error_message = "Volume size must be between 20 GB and 30 GB to remain within the AWS Free Tier."
  }
}

variable "admin_source_cidr" {
  type        = string
  description = "Administrator IP address in CIDR format (/32) allowed SSH access."
  default     = "0.0.0.0/0"

  validation {
    condition     = can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}/(?:32|24|0)$", var.admin_source_cidr))
    error_message = "admin_source_cidr must be a valid IPv4 CIDR notation (e.g. 203.0.113.10/32)."
  }
}

variable "key_name" {
  type        = string
  description = "Name of an existing AWS Key Pair for SSH access (optional)."
  default     = ""
}

