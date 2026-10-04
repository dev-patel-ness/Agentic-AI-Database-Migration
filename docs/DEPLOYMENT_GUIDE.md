# AWS Deployment Guide — Agentic AI Database Migration Platform

## Overview

This guide covers deploying the complete Capstone platform to AWS EKS with RDS, Bedrock integration, and full observability (LangSmith, Prometheus, Grafana).

**Target Architecture:**
- VPC: 10.0.0.0/16 with 3 tiers (public, private, database subnets)
- EKS: Kubernetes 1.28, 2 node groups (platform: t3.large/2 replicas; app: t3.xlarge/3 replicas)
- RDS: PostgreSQL 15.3 (target), MySQL 8.0.35, Oracle 23.2.0.0 (sources), Multi-AZ
- IAM: IRSA for pod-to-AWS credential passing (no plaintext env vars)
- Secrets Manager: Runtime DB/Bedrock/LangSmith credential storage
- GitHub Actions: 6-stage CI/CD pipeline (lint → test → build → scan → staging → E2E → approval → prod)

**Prerequisites:**
- AWS account with Bedrock model access (Nova Pro, Titan Embeddings)
- Terraform ≥ 1.0
- kubectl ≥ 1.28
- Helm ≥ 3.10
- GitHub Actions enabled (for CI/CD)
- Docker (for local image builds)

---

## Phase 1: Infrastructure Setup (30 minutes)

### 1.1 Initialize Terraform State Backend

```bash
cd infra/terraform

# Create S3 bucket for Terraform state (one-time setup)
aws s3api create-bucket \
  --bucket capstone-terraform-state-${ACCOUNT_ID} \
  --region ${AWS_REGION} \
  --create-bucket-configuration LocationConstraint=${AWS_REGION}

# Enable versioning on state bucket
aws s3api put-bucket-versioning \
  --bucket capstone-terraform-state-${ACCOUNT_ID} \
  --versioning-configuration Status=Enabled

# Block public access
aws s3api put-public-access-block \
  --bucket capstone-terraform-state-${ACCOUNT_ID} \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# Create DynamoDB table for state locking
aws dynamodb create-table \
  --table-name capstone-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region ${AWS_REGION}
```

### 1.2 Configure Terraform Variables

```bash
# Copy template and update with your values
cp terraform.tfvars.example terraform.tfvars

# Edit terraform.tfvars with:
cat >> terraform.tfvars <<EOF
aws_region           = "${AWS_REGION}"
environment          = "prod"
cluster_version      = "1.28"
rds_multi_az         = true
tf_backend_bucket    = "capstone-terraform-state-${ACCOUNT_ID}"
tf_backend_key       = "prod/terraform.tfstate"
tf_backend_lock_table = "capstone-terraform-locks"
EOF
```

### 1.3 Deploy Infrastructure

```bash
# Initialize Terraform with S3 backend
terraform init \
  -backend-config="bucket=capstone-terraform-state-${ACCOUNT_ID}" \
  -backend-config="key=prod/terraform.tfstate" \
  -backend-config="region=${AWS_REGION}" \
  -backend-config="dynamodb_table=capstone-terraform-locks"

# Validate
terraform validate

# Plan (review before applying)
terraform plan -out=tfplan

# Apply (watch for ~20 minutes)
terraform apply tfplan

# Export outputs for later use
terraform output -json > /tmp/tf-outputs.json
```

**Expected Outputs:**
- EKS cluster endpoint
- RDS database endpoints (PostgreSQL, MySQL, Oracle)
- IAM role ARNs (deployment-agent, app-sa)
- VPC ID, subnet IDs, security group IDs

---

## Phase 2: Kubernetes Configuration (15 minutes)

### 2.1 Configure kubectl Access

```bash
# Get kubeconfig from Terraform output
EKS_CLUSTER_NAME=$(jq -r '.eks_cluster_name.value' /tmp/tf-outputs.json)
AWS_REGION=$(jq -r '.aws_region.value' /tmp/tf-outputs.json)

# Update kubeconfig
aws eks update-kubeconfig \
  --region ${AWS_REGION} \
  --name ${EKS_CLUSTER_NAME}

# Verify access
kubectl get nodes
```

### 2.2 Deploy Network Policies & Pod Security Policies

```bash
# Apply security policies
kubectl apply -f infra/k8s/network-policies.yaml
kubectl apply -f infra/k8s/pod-security-policy.yaml

# Verify
kubectl get networkpolicies -A
kubectl get psp capstone-restricted
```

### 2.3 Deploy Helm Charts

```bash
# Add Helm repos
helm repo add capstone local://infra/helm
helm repo update

# Create namespaces
kubectl create namespace ns-platform
kubectl create namespace ns-app

# Deploy platform (API + Orchestrator)
helm install capstone-platform infra/helm/capstone-platform \
  --namespace ns-platform \
  --values infra/helm/capstone-platform/values.yaml \
  --wait

# Deploy app (Streamlit UI)
helm install capstone-app infra/helm/capstone-app \
  --namespace ns-app \
  --values infra/helm/capstone-app/values.yaml \
  --wait

# Verify deployments
kubectl get pods -n ns-platform
kubectl get pods -n ns-app
```

---

## Phase 3: Secrets Configuration (10 minutes)

### 3.1 Create Secrets in AWS Secrets Manager

```bash
# PostgreSQL target credentials
aws secretsmanager create-secret \
  --name capstone-prod/postgresql-credentials \
  --secret-string '{
    "username": "postgres",
    "password": "SECURE_PASSWORD",
    "host": "capstone-prod.c9akciq32.us-east-1.rds.amazonaws.com",
    "port": 5432,
    "database": "capstone_target"
  }'

# MySQL source credentials
aws secretsmanager create-secret \
  --name capstone-prod/mysql-credentials \
  --secret-string '{
    "username": "migration",
    "password": "SECURE_PASSWORD",
    "host": "mysql-source.example.com",
    "port": 3306,
    "database": "source_db"
  }'

# Oracle source credentials
aws secretsmanager create-secret \
  --name capstone-prod/oracle-credentials \
  --secret-string '{
    "username": "migration",
    "password": "SECURE_PASSWORD",
    "host": "oracle-source.example.com",
    "port": 1521,
    "service_name": "XE"
  }'

# Bedrock configuration
aws secretsmanager create-secret \
  --name capstone-prod/bedrock-config \
  --secret-string '{
    "region": "us-east-1",
    "model_id": "us.amazon.nova-pro-v1:0"
  }'

# LangSmith configuration (optional)
aws secretsmanager create-secret \
  --name capstone-prod/langsmith-config \
  --secret-string '{
    "api_key": "LANGSMITH_API_KEY",
    "project": "capstone"
  }'
```

### 3.2 Verify IRSA Pod Access

```bash
# The ServiceAccounts in Helm charts already have IRSA annotations
# Verify that pods can assume IAM roles
kubectl -n ns-platform describe sa capstone-platform-sa | grep eks.amazonaws.com

# Test credential retrieval from within pod
kubectl -n ns-platform exec deployment/capstone-platform -- \
  python -c "
from observability.secrets_manager import get_secrets_manager
sm = get_secrets_manager()
creds = sm.get_db_credentials('capstone-prod', 'postgresql')
print('✓ PostgreSQL credentials retrieved:', creds['host'])
"
```

---

## Phase 4: Observability Stack (20 minutes)

### 4.1 Deploy Prometheus

```bash
# Create observability namespace
kubectl create namespace observability

# Add Prometheus Helm repo
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Deploy Prometheus
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace observability \
  --set prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.resources.requests.storage=10Gi \
  --wait

# Verify
kubectl get pods -n observability
```

### 4.2 Deploy Grafana

```bash
# Deploy Grafana (included in kube-prometheus-stack, but configure separately)
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

helm install grafana grafana/grafana \
  --namespace observability \
  --set adminPassword='SECURE_PASSWORD' \
  --set persistence.enabled=true \
  --set persistence.size=10Gi \
  --wait

# Get Grafana URL
kubectl get svc -n observability grafana -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'

# Access: http://<GRAFANA_URL>:3000 (default: admin / SECURE_PASSWORD)
```

### 4.3 Import Grafana Dashboards

```bash
# Copy dashboard JSONs to Grafana (via API)
GRAFANA_URL=$(kubectl get svc -n observability grafana -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
GRAFANA_PASS='SECURE_PASSWORD'

for dashboard in observability/grafana-dashboards/*.json; do
  curl -X POST \
    http://admin:${GRAFANA_PASS}@${GRAFANA_URL}:3000/api/dashboards/db \
    -H "Content-Type: application/json" \
    -d @${dashboard}
done

echo "✓ Grafana dashboards imported"
```

### 4.4 Configure LangSmith (optional)

```bash
# LangSmith integration is automatic if credentials are in Secrets Manager
# No additional setup required — traces will appear at https://smith.langchain.com

# Verify in LangSmith UI:
# 1. Project: capstone
# 2. Traces by agent (discovery, planner, schema)
# 3. LLM calls with tokens, latency, cost
```

---

## Phase 5: CI/CD Pipeline Setup (15 minutes)

### 5.1 Configure GitHub Secrets

In your GitHub repo (Settings → Secrets and variables):

```
AWS_STAGING_ROLE_ARN       # OIDC role for staging deploy
AWS_PROD_ROLE_ARN          # OIDC role for prod deploy
TF_BACKEND_BUCKET          # S3 bucket name
TF_BACKEND_LOCK_TABLE      # DynamoDB table name
BEDROCK_MODEL_ID           # us.amazon.nova-pro-v1:0
LANGSMITH_API_KEY          # LangSmith project API key (optional)
```

### 5.2 Configure OIDC Provider for GitHub Actions

```bash
# Terraform already created the OIDC provider (see iam.tf)
# Verify it exists:
aws iam list-open-id-connect-providers

# The OIDC provider ARN and thumbprint are in Terraform outputs
```

### 5.3 Push Code and Trigger Pipeline

```bash
# Push to develop branch to trigger staging deploy
git push origin develop

# Monitor pipeline in GitHub Actions
# Expected flow: lint → test → build → scan → deploy-staging → e2e → manual-approval

# Once approved, push to main to deploy to production
git push origin main
```

---

## Phase 6: Verify Deployment (10 minutes)

### 6.1 Check All Services are Running

```bash
# Platform namespace
kubectl get all -n ns-platform
kubectl logs -n ns-platform deployment/capstone-platform --tail=50

# App namespace
kubectl get all -n ns-app
kubectl logs -n ns-app deployment/capstone-app --tail=50

# Observability
kubectl get all -n observability
```

### 6.2 Test API Endpoint

```bash
# Get API load balancer URL
API_URL=$(kubectl get svc -n ns-platform capstone-platform \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

# Health check
curl http://${API_URL}:8000/health

# API docs
echo "API Docs: http://${API_URL}:8000/docs"
```

### 6.3 Test UI Endpoint

```bash
# Get UI load balancer URL
UI_URL=$(kubectl get svc -n ns-app capstone-app \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

# Access UI
echo "Streamlit UI: http://${UI_URL}:8501"
```

### 6.4 Test Database Connectivity

```bash
# Connect to RDS PostgreSQL target
psql -h $(jq -r '.rds_postgres_endpoint.value' /tmp/tf-outputs.json) \
     -U postgres \
     -d capstone_target \
     -c "SELECT version();"

# Verify Secrets Manager integration
kubectl -n ns-platform exec deployment/capstone-platform -- \
  python -c "
from observability.secrets_manager import get_secrets_manager
sm = get_secrets_manager()
print('✓ Secrets Manager connected')
print('✓ Credentials cached and ready')
"
```

---

## Phase 7: Run Live Demo (10 minutes)

```bash
# Execute the live demo script
bash scripts/demo-live.sh

# This will orchestrate a complete Oracle → PostgreSQL migration showing:
# - Phase 2: Schema discovery
# - Phase 3: Migration planning + approval
# - Phase 4: DDL translation (Bedrock)
# - Phase 5: Data migration
# - Phase 7: Validation
# - Phase 8: Deployment with rollback
# - Phase 9: Observability & dashboards
```

---

## Phase 8: Production Monitoring (Ongoing)

### 8.1 Grafana Dashboards

Access at: `http://<GRAFANA_URL>:3000`

- **Agent Cost & Latency**: Agent execution times (p50/p95/p99), LLM token usage, cost estimation
- **Tool Success Rate**: Schema extractor, CrackSQL, SeaTunnel, terraform, kubectl success rates
- **Pod Health**: Ready/desired replicas, restart counts, namespace status
- **Deployment Rollout**: Rolling update duration, rollback events, success rate

### 8.2 LangSmith Traces

Access at: `https://smith.langchain.com`

- Filter by project: `capstone`
- View agent execution traces with latency and cost
- Track LLM calls with token usage

### 8.3 Alarms & Notifications

```bash
# Create CloudWatch alarms for critical metrics
aws cloudwatch put-metric-alarm \
  --alarm-name capstone-pod-restart-count \
  --alarm-actions arn:aws:sns:${AWS_REGION}:${ACCOUNT_ID}:capstone-alerts \
  --metric-name pod_restart_count \
  --namespace prometheus \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold

# Similar alarms for:
# - EKS node health
# - RDS database connectivity
# - Bedrock API errors
# - Deployment rollback triggers
```

---

## Phase 9: Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| Pods stuck in Pending | Check node resources: `kubectl top nodes` and increase node group size |
| RDS connectivity failed | Verify security groups allow EKS pod subnets; check credentials in Secrets Manager |
| Bedrock errors (AccessDenied) | Verify IAM role has `bedrock:InvokeModel` permission; check IRSA annotations |
| Helm chart install fails | Run `helm lint` on chart; check namespace exists; verify RBAC permissions |
| LangSmith traces not appearing | Verify credentials in Secrets Manager; check network egress allows smith.langchain.com |
| Deployment rollback triggered | Check pod logs: `kubectl logs <pod> -n ns-platform`; review Prometheus metrics for anomalies |

### Debug Commands

```bash
# Pod logs
kubectl logs -n ns-platform deployment/capstone-platform -f

# Describe pod for events
kubectl describe pod -n ns-platform <pod-name>

# Check IRSA role assumption
kubectl -n ns-platform exec deployment/capstone-platform -- \
  env | grep AWS_ROLE_ARN

# SSH into pod for debugging
kubectl exec -it -n ns-platform deployment/capstone-platform -- /bin/bash

# Check secret access
kubectl -n ns-platform exec deployment/capstone-platform -- \
  aws secretsmanager get-secret-value --secret-id capstone-prod/postgresql-credentials

# Monitor pod restart count
watch kubectl get pods -n ns-platform -o wide
```

---

## Phase 10: Scaling & Optimization

### Auto-Scaling

Helm charts already include HPA (Horizontal Pod Autoscaler):
- **capstone-platform**: 2-5 replicas (70% CPU, 80% memory)
- **capstone-app**: 3-10 replicas (70% CPU, 80% memory)

Monitor scaling in Grafana dashboard.

### Cost Optimization

```bash
# Reserved Instances for node groups (reduce compute costs ~40%)
aws ec2 purchase-reserved-instances \
  --instance-count 2 \
  --instance-type t3.large \
  --offering-class all-upfront

# RDS Read Replicas for scale-out (optional)
aws rds create-db-instance-read-replica \
  --db-instance-identifier capstone-read-replica-1 \
  --source-db-instance-identifier capstone-prod
```

---

## Cleanup

To destroy infrastructure and avoid AWS charges:

```bash
# Destroy EKS, RDS, VPC, IAM roles
cd infra/terraform
terraform destroy -auto-approve

# Cleanup S3 state bucket
aws s3 rb s3://capstone-terraform-state-${ACCOUNT_ID} --force

# Cleanup Secrets Manager
aws secretsmanager delete-secret \
  --secret-id capstone-prod/postgresql-credentials \
  --force-delete-without-recovery
```

---

## Next Steps

1. ✅ Infrastructure deployed (Phase 1-2)
2. ✅ Secrets & IRSA configured (Phase 3)
3. ✅ Observability stack running (Phase 4)
4. ✅ CI/CD pipeline active (Phase 5)
5. 🚀 Run live migrations (Phase 10)
6. 📊 Monitor dashboards in Grafana
7. 🔍 Review traces in LangSmith
8. 🔄 Iterate with user feedback

For questions or issues, refer to [architecture.md](../architecture.md) and [plan.md](../plan.md).
