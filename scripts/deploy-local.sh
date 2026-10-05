#!/usr/bin/env bash
# Build the image and deploy it to a local Kubernetes cluster (minikube / kind / Docker Desktop).
# Usage: ./scripts/deploy-local.sh
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="$(cat VERSION)"
IMAGE="restaurant-management:${VERSION}"

echo ">> Building ${IMAGE}"
docker build -t "${IMAGE}" .

if command -v minikube >/dev/null 2>&1 && minikube status >/dev/null 2>&1; then
  echo ">> Loading image into minikube"
  minikube image load "${IMAGE}"
elif command -v kind >/dev/null 2>&1 && kind get clusters 2>/dev/null | grep -q .; then
  echo ">> Loading image into kind"
  kind load docker-image "${IMAGE}"
fi

echo ">> Applying manifests"
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml -f k8s/pvc.yaml -f k8s/service.yaml
sed "s|image: restaurant-management:.*|image: ${IMAGE}|" k8s/deployment.yaml | kubectl apply -f -

echo ">> Waiting for rollout"
kubectl -n restaurant rollout status deployment/restaurant-app --timeout=180s
kubectl -n restaurant get pods,svc
echo
echo "Open the app with:  kubectl -n restaurant port-forward svc/restaurant-service 8080:80"
echo "then browse http://localhost:8080"
