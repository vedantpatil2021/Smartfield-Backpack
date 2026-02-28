#!/usr/bin/env bash
set -euo pipefail

helm upgrade --install smartfield charts/smartfield \
  --namespace smartfield \
  --create-namespace \
  --wait \
  --timeout 300s

echo "Deployment complete."
kubectl -n smartfield get pods
