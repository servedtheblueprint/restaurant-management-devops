#!/usr/bin/env bash
# Roll the deployment back to the previous revision.
set -euo pipefail
kubectl -n restaurant rollout undo deployment/restaurant-app
kubectl -n restaurant rollout status deployment/restaurant-app --timeout=120s
