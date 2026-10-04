###############################################################################
# Outputs - EKS Cluster
###############################################################################

output "cluster_id" {
  description = "EKS cluster ID"
  value       = aws_eks_cluster.main.id
}

output "cluster_name" {
  description = "EKS cluster name"
  value       = aws_eks_cluster.main.name
}

output "cluster_arn" {
  description = "EKS cluster ARN"
  value       = aws_eks_cluster.main.arn
}

output "cluster_endpoint" {
  description = "EKS cluster endpoint"
  value       = aws_eks_cluster.main.endpoint
}

output "cluster_ca_certificate" {
  description = "EKS cluster CA certificate (base64 encoded)"
  value       = aws_eks_cluster.main.certificate_authority[0].data
  sensitive   = true
}

output "cluster_version" {
  description = "EKS cluster Kubernetes version"
  value       = aws_eks_cluster.main.version
}

output "cluster_status" {
  description = "EKS cluster status"
  value       = aws_eks_cluster.main.status
}

###############################################################################
# Outputs - VPC
###############################################################################

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "vpc_cidr" {
  description = "VPC CIDR block"
  value       = aws_vpc.main.cidr_block
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = aws_subnet.private[*].id
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = aws_subnet.public[*].id
}

output "database_subnet_ids" {
  description = "Database subnet IDs"
  value       = aws_subnet.database[*].id
}

###############################################################################
# Outputs - Security Groups
###############################################################################

output "eks_control_plane_sg_id" {
  description = "EKS control plane security group ID"
  value       = aws_security_group.eks_control_plane.id
}

output "eks_nodes_sg_id" {
  description = "EKS nodes security group ID"
  value       = aws_security_group.eks_nodes.id
}

output "rds_sg_id" {
  description = "RDS security group ID"
  value       = aws_security_group.rds.id
}

output "alb_sg_id" {
  description = "ALB security group ID"
  value       = aws_security_group.alb.id
}

###############################################################################
# Outputs - RDS Databases
###############################################################################

output "postgres_target_endpoint" {
  description = "PostgreSQL target database endpoint"
  value       = aws_db_instance.postgres_target.endpoint
}

output "postgres_target_address" {
  description = "PostgreSQL target database address"
  value       = aws_db_instance.postgres_target.address
}

output "postgres_target_port" {
  description = "PostgreSQL target database port"
  value       = aws_db_instance.postgres_target.port
}

output "postgres_target_dbname" {
  description = "PostgreSQL target database name"
  value       = aws_db_instance.postgres_target.db_name
}

output "mysql_source_endpoint" {
  description = "MySQL source database endpoint"
  value       = aws_db_instance.mysql_source.endpoint
}

output "mysql_source_address" {
  description = "MySQL source database address"
  value       = aws_db_instance.mysql_source.address
}

output "mysql_source_port" {
  description = "MySQL source database port"
  value       = aws_db_instance.mysql_source.port
}

output "mysql_source_dbname" {
  description = "MySQL source database name"
  value       = aws_db_instance.mysql_source.db_name
}

output "oracle_source_endpoint" {
  description = "Oracle source database endpoint"
  value       = aws_db_instance.oracle_source.endpoint
}

output "oracle_source_address" {
  description = "Oracle source database address"
  value       = aws_db_instance.oracle_source.address
}

output "oracle_source_port" {
  description = "Oracle source database port"
  value       = aws_db_instance.oracle_source.port
}

###############################################################################
# Outputs - Database Credentials
###############################################################################

output "db_credentials_secret_arn" {
  description = "ARN of Secrets Manager secret containing database credentials"
  value       = aws_secretsmanager_secret.db_credentials.arn
}

output "db_credentials_secret_name" {
  description = "Name of Secrets Manager secret containing database credentials"
  value       = aws_secretsmanager_secret.db_credentials.name
}

###############################################################################
# Outputs - IAM Roles
###############################################################################

output "deployment_agent_role_arn" {
  description = "Deployment Agent IRSA role ARN"
  value       = aws_iam_role.deployment_agent_sa.arn
}

output "app_role_arn" {
  description = "App pods IRSA role ARN"
  value       = aws_iam_role.app_sa.arn
}

output "eks_node_role_arn" {
  description = "EKS node role ARN"
  value       = aws_iam_role.eks_node_role.arn
}

###############################################################################
# Outputs - OIDC Provider
###############################################################################

output "oidc_provider_arn" {
  description = "OIDC provider ARN for IRSA"
  value       = aws_iam_openid_connect_provider.cluster.arn
}

output "oidc_provider_url" {
  description = "OIDC provider URL"
  value       = aws_iam_openid_connect_provider.cluster.url
}

###############################################################################
# Outputs - CloudWatch Logs
###############################################################################

output "eks_log_group_name" {
  description = "CloudWatch log group for EKS cluster"
  value       = aws_cloudwatch_log_group.eks.name
}

output "rds_log_group_name" {
  description = "CloudWatch log group for RDS"
  value       = aws_cloudwatch_log_group.rds.name
}

###############################################################################
# Outputs - Configuration for kubeconfig
###############################################################################

output "configure_kubectl" {
  description = "Command to update kubeconfig"
  value       = "aws eks update-kubeconfig --name ${aws_eks_cluster.main.name} --region ${var.aws_region}"
}
