###############################################################################
# Service Account IRSA Roles
###############################################################################

# Deployment Agent Service Account Role
resource "aws_iam_role" "deployment_agent_sa" {
  name = "${local.cluster_name}-deployment-agent-sa"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRoleWithWebIdentity"
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.cluster.arn
        }
        Condition = {
          StringEquals = {
            "${replace(aws_iam_openid_connect_provider.cluster.url, "https://", "")}:sub" = "system:serviceaccount:ns-platform:deployment-agent"
            "${replace(aws_iam_openid_connect_provider.cluster.url, "https://", "")}:aud" = "sts.amazonaws.com"
          }
        }
      }
    ]
  })

  tags = local.common_tags
}

# Deployment Agent Policy: kubectl operations on ns-app only
resource "aws_iam_role_policy" "deployment_agent_kubectl" {
  name = "${local.cluster_name}-deployment-agent-kubectl"
  role = aws_iam_role.deployment_agent_sa.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "eks:DescribeCluster",
          "eks:ListClusters"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeSecurityGroups",
          "ec2:DescribeSubnets",
          "ec2:DescribeVpcs"
        ]
        Resource = "*"
      }
    ]
  })
}

# Deployment Agent Policy: Terraform operations
resource "aws_iam_role_policy" "deployment_agent_terraform" {
  name = "${local.cluster_name}-deployment-agent-terraform"
  role = aws_iam_role.deployment_agent_sa.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::capstone-terraform-state",
          "arn:aws:s3:::capstone-terraform-state/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:DeleteItem"
        ]
        Resource = "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/terraform-locks"
      }
    ]
  })
}

# Deployment Agent Policy: Database connections for health checks
resource "aws_iam_role_policy" "deployment_agent_db" {
  name = "${local.cluster_name}-deployment-agent-db"
  role = aws_iam_role.deployment_agent_sa.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "rds:DescribeDBInstances",
          "rds:DescribeDBClusters",
          "rds-db:connect"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = aws_secretsmanager_secret.db_credentials.arn
      }
    ]
  })
}

# Application Service Account Role (for app pods to access AWS resources)
resource "aws_iam_role" "app_sa" {
  name = "${local.cluster_name}-app-sa"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRoleWithWebIdentity"
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.cluster.arn
        }
        Condition = {
          StringEquals = {
            "${replace(aws_iam_openid_connect_provider.cluster.url, "https://", "")}:sub" = "system:serviceaccount:ns-app:default"
            "${replace(aws_iam_openid_connect_provider.cluster.url, "https://", "")}:aud" = "sts.amazonaws.com"
          }
        }
      }
    ]
  })

  tags = local.common_tags
}

# App Pod Policy: Database access via IAM DB auth (PostgreSQL only)
resource "aws_iam_role_policy" "app_rds_db_auth" {
  name = "${local.cluster_name}-app-rds-db-auth"
  role = aws_iam_role.app_sa.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "rds-db:connect"
        ]
        Resource = [
          "arn:aws:rds:${var.aws_region}:${data.aws_caller_identity.current.account_id}:db/${aws_db_instance.postgres_target.identifier}"
        ]
      }
    ]
  })
}

# App Pod Policy: Bedrock access for AI operations
resource "aws_iam_role_policy" "app_bedrock" {
  name = "${local.cluster_name}-app-bedrock"
  role = aws_iam_role.app_sa.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock-runtime:InvokeModel",
          "bedrock-runtime:InvokeModelWithResponseStream"
        ]
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/*"
      }
    ]
  })
}

# App Pod Policy: Secrets Manager access
resource "aws_iam_role_policy" "app_secrets" {
  name = "${local.cluster_name}-app-secrets"
  role = aws_iam_role.app_sa.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = [
          aws_secretsmanager_secret.db_credentials.arn,
          "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${local.cluster_name}/*"
        ]
      }
    ]
  })
}

# App Pod Policy: CloudWatch Logs
resource "aws_iam_role_policy" "app_logs" {
  name = "${local.cluster_name}-app-logs"
  role = aws_iam_role.app_sa.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/eks/${local.cluster_name}/*"
      }
    ]
  })
}

###############################################################################
# S3 Bucket for Terraform State (if not already created)
###############################################################################

resource "aws_s3_bucket" "terraform_state" {
  count  = var.environment == "staging" ? 1 : 0
  bucket = "capstone-terraform-state-${data.aws_caller_identity.current.account_id}"

  tags = merge(
    local.common_tags,
    {
      Name = "capstone-terraform-state"
    }
  )
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  count  = var.environment == "staging" ? 1 : 0
  bucket = aws_s3_bucket.terraform_state[0].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  count  = var.environment == "staging" ? 1 : 0
  bucket = aws_s3_bucket.terraform_state[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "terraform_state" {
  count  = var.environment == "staging" ? 1 : 0
  bucket = aws_s3_bucket.terraform_state[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

###############################################################################
# DynamoDB Table for Terraform State Locking
###############################################################################

resource "aws_dynamodb_table" "terraform_locks" {
  count          = var.environment == "staging" ? 1 : 0
  name           = "terraform-locks"
  hash_key       = "LockID"
  billing_mode   = "PAY_PER_REQUEST"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = merge(
    local.common_tags,
    {
      Name = "terraform-locks"
    }
  )
}
