###############################################################################
# AWS Region & Cluster Configuration
###############################################################################

variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "staging"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "capstone-migration"
}

variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
  default     = ""
}

variable "cluster_version" {
  description = "EKS cluster Kubernetes version"
  type        = string
  default     = "1.28"
}

variable "cluster_endpoint_private_access" {
  description = "Enable private API server endpoint"
  type        = bool
  default     = true
}

variable "cluster_endpoint_public_access" {
  description = "Enable public API server endpoint"
  type        = bool
  default     = true
}

###############################################################################
# VPC Configuration
###############################################################################

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of availability zones"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]
}

variable "database_subnet_cidrs" {
  description = "CIDR blocks for database subnets"
  type        = list(string)
  default     = ["10.0.201.0/24", "10.0.202.0/24", "10.0.203.0/24"]
}

###############################################################################
# EKS Node Group Configuration
###############################################################################

variable "node_groups" {
  description = "Map of node group configurations"
  type = map(object({
    name           = string
    desired_size   = number
    min_size       = number
    max_size       = number
    instance_types = list(string)
    disk_size      = number
    labels         = map(string)
  }))
  default = {
    "platform" = {
      name           = "platform-nodes"
      desired_size   = 2
      min_size       = 1
      max_size       = 3
      instance_types = ["t3.large"]
      disk_size      = 50
      labels = {
        workload = "platform"
      }
    }
    "app" = {
      name           = "app-nodes"
      desired_size   = 3
      min_size       = 1
      max_size       = 5
      instance_types = ["t3.xlarge"]
      disk_size      = 100
      labels = {
        workload = "app"
      }
    }
  }
}

###############################################################################
# RDS Configuration
###############################################################################

variable "rds_postgres_instance_class" {
  description = "RDS PostgreSQL instance class"
  type        = string
  default     = "db.t3.medium"
}

variable "rds_mysql_instance_class" {
  description = "RDS MySQL instance class"
  type        = string
  default     = "db.t3.medium"
}

variable "rds_oracle_instance_class" {
  description = "RDS Oracle instance class"
  type        = string
  default     = "db.t3.large"
}

variable "rds_allocated_storage" {
  description = "Allocated storage for RDS instances (GB)"
  type        = number
  default     = 50
}

variable "rds_engine_version_postgres" {
  description = "PostgreSQL engine version"
  type        = string
  default     = "15.3"
}

variable "rds_engine_version_mysql" {
  description = "MySQL engine version"
  type        = string
  default     = "8.0.35"
}

variable "rds_engine_version_oracle" {
  description = "Oracle engine version"
  type        = string
  default     = "23.2.0.0"
}

variable "rds_backup_retention_days" {
  description = "RDS backup retention period in days"
  type        = number
  default     = 7
}

variable "rds_multi_az" {
  description = "Enable Multi-AZ for RDS"
  type        = bool
  default     = true
}

###############################################################################
# Database Master Credentials (sourced from environment or AWS Secrets Manager)
###############################################################################

variable "db_master_username" {
  description = "Master database username"
  type        = string
  sensitive   = true
  default     = "admin"
}

variable "db_master_password" {
  description = "Master database password"
  type        = string
  sensitive   = true
}

###############################################################################
# Application Configuration
###############################################################################

variable "app_replicas" {
  description = "Number of app pod replicas"
  type        = number
  default     = 3
}

variable "enable_monitoring" {
  description = "Enable Prometheus/Grafana monitoring"
  type        = bool
  default     = true
}

variable "enable_logging" {
  description = "Enable CloudWatch container logging"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default = {
    Project     = "capstone-migration"
    Environment = "staging"
    ManagedBy   = "terraform"
  }
}
