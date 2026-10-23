terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    cloudinit = {
      source  = "hashicorp/cloudinit"
      version = "~> 2.3"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# --- Network (VPC, IGW, Subnet) ---
resource "aws_vpc" "rootlens_vpc" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "rootlens-free-tier-vpc"
    Project     = "RootLens"
    Environment = "Production"
  }
}

resource "aws_internet_gateway" "rootlens_igw" {
  vpc_id = aws_vpc.rootlens_vpc.id

  tags = {
    Name    = "rootlens-igw"
    Project = "RootLens"
  }
}

resource "aws_subnet" "rootlens_public_subnet" {
  vpc_id                  = aws_vpc.rootlens_vpc.id
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true
  availability_zone       = data.aws_availability_zones.available.names[0]

  tags = {
    Name    = "rootlens-public-subnet"
    Project = "RootLens"
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_route_table" "rootlens_public_rt" {
  vpc_id = aws_vpc.rootlens_vpc.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.rootlens_igw.id
  }

  tags = {
    Name    = "rootlens-public-rt"
    Project = "RootLens"
  }
}

resource "aws_route_table_association" "rootlens_public_rta" {
  subnet_id      = aws_subnet.rootlens_public_subnet.id
  route_table_id = aws_route_table.rootlens_public_rt.id
}

# --- Security Group ---
resource "aws_security_group" "rootlens_sg" {
  name        = "rootlens-security-group"
  description = "Allow inbound HTTP, HTTPS, and restricted SSH"
  vpc_id      = aws_vpc.rootlens_vpc.id

  ingress {
    description = "HTTP ingress"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS ingress"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "RootLens Web API Direct Port"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH from admin CIDR"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.admin_source_cidr]
  }

  egress {
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = {
    Name    = "rootlens-sg"
    Project = "RootLens"
  }
}

# --- AWS Free Tier Budget Guardrail ---
check "aws_free_tier_budget_check" {
  assert {
    condition     = var.instance_type == "t2.micro" || var.instance_type == "t3.micro" || var.instance_type == "t4g.small"
    error_message = "Selected instance_type must be a Free Tier eligible shape (t2.micro, t3.micro, or t4g.small)."
  }
  assert {
    condition     = var.root_volume_size_gb <= 30
    error_message = "Root EBS volume size exceeds the 30 GB AWS Free Tier limit."
  }
}

# --- AMI Lookup (Ubuntu 24.04 LTS) ---
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# --- Cloud-Init User Data for k3s & RootLens Bootstrapping ---
data "cloudinit_config" "rootlens_init" {
  gzip          = false
  base64_encode = false

  part {
    content_type = "text/x-shellscript"
    content      = <<-EOF
      #!/bin/bash
      set -euxo pipefail
      
      # Update and install Docker and prerequisites
      apt-get update -y
      apt-get install -y ca-certificates curl gnupg lsb-release git ufw
      
      # Install Docker Engine
      install -m 0755 -d /etc/apt/keyrings
      curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
      chmod a+r /etc/apt/keyrings/docker.gpg
      echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
      apt-get update -y
      apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
      
      # Install lightweight Kubernetes (k3s)
      curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--write-kubeconfig-mode 644 --disable traefik" sh -
      
      # Configure environment
      export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
      echo "export KUBECONFIG=/etc/rancher/k3s/k3s.yaml" >> /etc/environment
      
      # Wait for node readiness
      /usr/local/bin/kubectl wait --for=condition=Ready node --all --timeout=120s
      
      # Setup rootlens directory
      mkdir -p /opt/rootlens
      echo "RootLens free tier instance initialized successfully" > /opt/rootlens/init.status
    EOF
  }
}

# --- EC2 Instance (100% Free Tier Eligible) ---
resource "aws_instance" "rootlens_server" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.rootlens_public_subnet.id
  vpc_security_group_ids      = [aws_security_group.rootlens_sg.id]
  associate_public_ip_address = true
  key_name                    = var.key_name != "" ? var.key_name : null
  user_data                   = data.cloudinit_config.rootlens_init.rendered

  root_block_device {
    volume_size           = var.root_volume_size_gb
    volume_type           = "gp3"
    delete_on_termination = true
    encrypted             = true

    tags = {
      Name    = "rootlens-root-volume"
      Project = "RootLens"
    }
  }

  tags = {
    Name        = "rootlens-free-tier-server"
    Project     = "RootLens"
    Environment = "Production"
  }
}

# --- Elastic IP (Free Tier when attached to running instance) ---
resource "aws_eip" "rootlens_eip" {
  instance = aws_instance.rootlens_server.id
  domain   = "vpc"

  tags = {
    Name    = "rootlens-eip"
    Project = "RootLens"
  }
}

