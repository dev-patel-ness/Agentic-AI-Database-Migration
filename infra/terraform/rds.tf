###############################################################################
# RDS DB Subnet Group
###############################################################################

resource "aws_db_subnet_group" "main" {
  name       = "${local.cluster_name}-db-subnet-group"
  subnet_ids = aws_subnet.database[*].id

  tags = merge(
    local.common_tags,
    {
      Name = "${local.cluster_name}-db-subnet-group"
    }
  )
}

###############################################################################
# RDS PostgreSQL Instance (Target Database)
###############################################################################

resource "aws_db_instance" "postgres_target" {
  identifier     = "${local.cluster_name}-postgres-target"
  engine         = "postgres"
  engine_version = var.rds_engine_version_postgres
  instance_class = var.rds_postgres_instance_class

  allocated_storage = var.rds_allocated_storage
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = "targetdb"
  username = var.db_master_username
  password = var.db_master_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  multi_az               = var.rds_multi_az
  publicly_accessible    = false
  backup_retention_days  = var.rds_backup_retention_days
  backup_window          = "03:00-04:00"
  maintenance_window     = "sun:04:00-sun:05:00"
  copy_tags_to_snapshot  = true
  skip_final_snapshot    = var.environment != "prod"
  final_snapshot_identifier = var.environment != "prod" ? null : "${local.cluster_name}-postgres-final-snapshot"
  
  # Performance Insights
  performance_insights_enabled = true
  monitoring_interval          = 60
  monitoring_role_arn          = aws_iam_role.rds_monitoring.arn

  enable_cloudwatch_logs_exports = ["postgresql"]
  log_retention_in_days          = 7

  depends_on = [aws_db_subnet_group.main]

  tags = merge(
    local.common_tags,
    {
      Name = "${local.cluster_name}-postgres-target"
    }
  )
}

###############################################################################
# RDS MySQL Instance (Source Database)
###############################################################################

resource "aws_db_instance" "mysql_source" {
  identifier     = "${local.cluster_name}-mysql-source"
  engine         = "mysql"
  engine_version = var.rds_engine_version_mysql
  instance_class = var.rds_mysql_instance_class

  allocated_storage = var.rds_allocated_storage
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = "sourcedb"
  username = var.db_master_username
  password = var.db_master_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  multi_az               = var.rds_multi_az
  publicly_accessible    = false
  backup_retention_days  = var.rds_backup_retention_days
  backup_window          = "03:00-04:00"
  maintenance_window     = "sun:04:00-sun:05:00"
  copy_tags_to_snapshot  = true
  skip_final_snapshot    = var.environment != "prod"
  final_snapshot_identifier = var.environment != "prod" ? null : "${local.cluster_name}-mysql-final-snapshot"
  
  # Performance Insights
  performance_insights_enabled = true
  monitoring_interval          = 60
  monitoring_role_arn          = aws_iam_role.rds_monitoring.arn

  enable_cloudwatch_logs_exports = ["error", "general", "slowquery"]

  depends_on = [aws_db_subnet_group.main]

  tags = merge(
    local.common_tags,
    {
      Name = "${local.cluster_name}-mysql-source"
    }
  )
}

###############################################################################
# RDS Oracle Instance (Source Database)
###############################################################################

resource "aws_db_instance" "oracle_source" {
  identifier     = "${local.cluster_name}-oracle-source"
  engine         = "oracle-se2"
  engine_version = var.rds_engine_version_oracle
  instance_class = var.rds_oracle_instance_class

  allocated_storage = var.rds_allocated_storage
  storage_type      = "gp3"
  storage_encrypted = true

  username = var.db_master_username
  password = var.db_master_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  multi_az               = var.rds_multi_az
  publicly_accessible    = false
  backup_retention_days  = var.rds_backup_retention_days
  backup_window          = "03:00-04:00"
  maintenance_window     = "sun:04:00-sun:05:00"
  copy_tags_to_snapshot  = true
  skip_final_snapshot    = var.environment != "prod"
  final_snapshot_identifier = var.environment != "prod" ? null : "${local.cluster_name}-oracle-final-snapshot"
  
  # Performance Insights
  performance_insights_enabled = true
  monitoring_interval          = 60
  monitoring_role_arn          = aws_iam_role.rds_monitoring.arn

  enable_cloudwatch_logs_exports = ["alert", "audit", "trace", "listener"]

  # Oracle-specific parameters
  option_group_name = aws_db_option_group.oracle.name
  parameter_group_name = aws_db_parameter_group.oracle.name

  depends_on = [aws_db_subnet_group.main]

  tags = merge(
    local.common_tags,
    {
      Name = "${local.cluster_name}-oracle-source"
    }
  )
}

###############################################################################
# Oracle Option Group
###############################################################################

resource "aws_db_option_group" "oracle" {
  name                     = "${local.cluster_name}-oracle-options"
  option_group_description = "Option group for Oracle DB instance"
  engine_name              = "oracle-se2"
  major_engine_version     = "23"

  tags = merge(
    local.common_tags,
    {
      Name = "${local.cluster_name}-oracle-options"
    }
  )
}

###############################################################################
# Oracle Parameter Group
###############################################################################

resource "aws_db_parameter_group" "oracle" {
  name        = "${local.cluster_name}-oracle-params"
  family      = "oracle-se2-23"
  description = "Custom parameter group for Oracle DB instance"

  # Enable archiving for CDC
  parameter {
    name  = "log_archive_dest_1"
    value = "LOCATION=/rdsdbdata/log USE_DB_RECOVERY_FILE_DEST VALID_FOR=(ALL_LOGFILES,ALL_ROLES) DB_RECOVERY_FILE_DEST_SIZE=100G"
  }

  tags = merge(
    local.common_tags,
    {
      Name = "${local.cluster_name}-oracle-params"
    }
  )
}

###############################################################################
# RDS Monitoring IAM Role
###############################################################################

resource "aws_iam_role" "rds_monitoring" {
  name = "${local.cluster_name}-rds-monitoring-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "monitoring.rds.amazonaws.com"
        }
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  role       = aws_iam_role.rds_monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

###############################################################################
# Database Security: Secrets Manager for Credentials
###############################################################################

resource "aws_secretsmanager_secret" "db_credentials" {
  name                    = "${local.cluster_name}/db-credentials"
  recovery_window_in_days = 7
  description             = "Database master credentials for ${local.cluster_name}"

  tags = merge(
    local.common_tags,
    {
      Name = "${local.cluster_name}-db-credentials"
    }
  )
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username              = var.db_master_username
    password              = var.db_master_password
    postgres_endpoint     = aws_db_instance.postgres_target.endpoint
    postgres_port         = 5432
    postgres_dbname       = aws_db_instance.postgres_target.db_name
    mysql_endpoint        = aws_db_instance.mysql_source.endpoint
    mysql_port            = 3306
    mysql_dbname          = aws_db_instance.mysql_source.db_name
    oracle_endpoint       = aws_db_instance.oracle_source.endpoint
    oracle_port           = 1521
  })
}

###############################################################################
# RDS Enhanced Monitoring
###############################################################################

resource "aws_cloudwatch_log_group" "rds" {
  name              = "/aws/rds/${local.cluster_name}"
  retention_in_days = 7

  tags = merge(
    local.common_tags,
    {
      Name = "${local.cluster_name}-rds-logs"
    }
  )
}
