terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.11"
    }
  }

  backend "s3" {
    # Configure these via backend config when running terraform init
    # Example: terraform init -backend-config="bucket=my-bucket" -backend-config="key=capstone/terraform.tfstate"
    # For local development, remove this block and comment out to use local state
    # bucket         = "capstone-terraform-state"
    # key            = "capstone/terraform.tfstate"
    # region         = "us-east-1"
    # encrypt        = true
    # dynamodb_table = "terraform-locks"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = merge(
      var.tags,
      {
        Environment = var.environment
        ManagedBy   = "terraform"
        Timestamp   = timestamp()
      }
    )
  }
}

provider "kubernetes" {
  host                   = aws_eks_cluster.main.endpoint
  cluster_ca_certificate = base64decode(aws_eks_cluster.main.certificate_authority[0].data)
  token                  = data.aws_eks_cluster_auth.main.token
}

provider "helm" {
  kubernetes {
    host                   = aws_eks_cluster.main.endpoint
    cluster_ca_certificate = base64decode(aws_eks_cluster.main.certificate_authority[0].data)
    token                  = data.aws_eks_cluster_auth.main.token
  }
}

# Data source for EKS cluster authentication
data "aws_eks_cluster_auth" "main" {
  name = aws_eks_cluster.main.name
}

# Data source for current AWS account
data "aws_caller_identity" "current" {}

# Data source for available AZs
data "aws_availability_zones" "available" {
  state = "available"
}

###############################################################################
# Local Variables
###############################################################################

locals {
  cluster_name            = var.cluster_name != "" ? var.cluster_name : "${var.project_name}-${var.environment}"
  eks_managed_policy_arns = [
    "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
    "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
  ]
  
  common_tags = merge(
    var.tags,
    {
      Environment = var.environment
      ClusterName = local.cluster_name
      ManagedBy   = "terraform"
    }
  )
}
