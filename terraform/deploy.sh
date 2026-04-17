#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# Build, push Docker image to ECR, terraform apply, then migrate SQLite data
#
# Prerequisites:
#   - AWS CLI v2 configured
#   - Docker running
#   - terraform >= 1.5
#   - DB_PASSWORD must be set
#
# Usage:
#   DB_PASSWORD=secret ./deploy.sh
#   DB_PASSWORD=secret SQLITE_PATH=/path/to/celebrities.db ./deploy.sh
###############################################################################

AWS_REGION="${AWS_REGION:-us-east-1}"
SERVICE_NAME="${SERVICE_NAME:-net-worth-game}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
DB_PASSWORD="${DB_PASSWORD:?DB_PASSWORD must be set}"
DB_NAME="${DB_NAME:-networth}"
DB_USERNAME="${DB_USERNAME:-networth}"
SQLITE_PATH="${SQLITE_PATH:-$HOME/net_worth_scraper/celebrities.db}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_FULL="${ECR_URI}/${SERVICE_NAME}:${IMAGE_TAG}"

echo "============================================="
echo " Net Worth Game API → Deploy"
echo "============================================="
echo "Region  : ${AWS_REGION}"
echo "Service : ${SERVICE_NAME}"
echo "Image   : ${IMAGE_FULL}"
echo "SQLite  : ${SQLITE_PATH}"
echo "============================================="

cd "${SCRIPT_DIR}"

echo ""
echo "▸ Step 1/5: terraform init"
terraform init -input=false

echo ""
echo "▸ Step 2/5: Ensure ECR exists"
terraform apply -input=false -auto-approve \
  -target=aws_ecr_repository.this \
  -var="aws_region=${AWS_REGION}" \
  -var="service_name=${SERVICE_NAME}" \
  -var="image_tag=${IMAGE_TAG}" \
  -var="db_password=${DB_PASSWORD}"

echo ""
echo "▸ Step 3/5: Build and push Docker image"
docker build --platform linux/amd64 -t "${SERVICE_NAME}:${IMAGE_TAG}" "${PROJECT_DIR}"

aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ECR_URI}"

docker tag "${SERVICE_NAME}:${IMAGE_TAG}" "${IMAGE_FULL}"
docker push "${IMAGE_FULL}"
echo "  ✓ Image pushed"

echo ""
echo "▸ Step 4/5: terraform apply (full — RDS + App Runner)"
terraform apply -input=false -auto-approve \
  -var="aws_region=${AWS_REGION}" \
  -var="service_name=${SERVICE_NAME}" \
  -var="image_tag=${IMAGE_TAG}" \
  -var="db_password=${DB_PASSWORD}"

echo ""
echo "▸ Step 5/5: Migrate SQLite data → RDS PostgreSQL"
RDS_HOST=$(terraform output -raw rds_endpoint)
DATABASE_URL="postgresql://${DB_USERNAME}:${DB_PASSWORD}@${RDS_HOST}:5432/${DB_NAME}"

echo "  Waiting 30s for RDS to be ready…"
sleep 30

cd "${PROJECT_DIR}"
DATABASE_URL="${DATABASE_URL}" python migrate_sqlite.py --sqlite "${SQLITE_PATH}"

echo ""
echo "============================================="
echo " ✓ Deployment complete!"
echo "============================================="
cd "${SCRIPT_DIR}"
terraform output
echo ""
echo "Set in WikiHover player config:"
APP_URL=$(terraform output -raw app_runner_url)
echo "  window.WikiHoverConfig.networthApi = \"${APP_URL}\""
