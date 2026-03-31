#!/bin/bash
# Deploy Crunchy Gherkins to GCP Compute Engine VM.
#
# Usage:
#   ./deploy.sh              Deploy to production
#   ./deploy.sh --build      Force rebuild all images
#
# Prerequisites:
#   - gcloud CLI configured with the correct project
#   - SSH access to the VM (gcloud compute ssh works)
#   - .env and service-account.json on the VM

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────
VM_NAME="${GCP_VM_NAME:-gacha-vm}"
VM_ZONE="${GCP_VM_ZONE:-us-central1-a}"
PROJECT_DIR="${GCP_PROJECT_DIR:-/home/$(gcloud config get-value account 2>/dev/null | cut -d@ -f1)/CrunchyGherkinsGachaBot}"
COMPOSE_CMD="docker compose --profile prod"

BUILD_FLAG=""
if [[ "${1:-}" == "--build" ]]; then
    BUILD_FLAG="--build"
fi

echo "🚀 Deploying Crunchy Gherkins to ${VM_NAME} (${VM_ZONE})"
echo "   Project dir: ${PROJECT_DIR}"
echo ""

# ── Deploy ───────────────────────────────────────────────────────────
gcloud compute ssh "${VM_NAME}" --zone="${VM_ZONE}" --command="
    set -euo pipefail
    cd ${PROJECT_DIR}

    echo '📥 Pulling latest code...'
    git pull --ff-only

    echo '🐳 Starting services...'
    ${COMPOSE_CMD} up -d ${BUILD_FLAG}

    echo ''
    echo '📊 Service status:'
    ${COMPOSE_CMD} ps

    echo ''
    echo '✅ Deployment complete!'
"
