# Restaurant Management System – Complete CI/CD (Project 16)

MSc IT Part 1 – DevOps. A small Flask application (restaurants, menu items, customers, orders)
wrapped in a complete DevOps toolchain.

| Requirement from the brief | Where it is |
|---|---|
| Git-based development | branching steps below, `.gitignore` |
| Automated builds / tests | `tests/test_api.py` (12 tests), run in CI |
| CI/CD | `.github/workflows/ci-cd.yml` (GitHub Actions) and `Jenkinsfile` (Jenkins) |
| Artifact versioning | `VERSION` file -> Docker tags `1.0.0`, `sha-xxxxxxx`, `latest` in GHCR |
| Docker Compose | `docker-compose.yml` |
| Kubernetes + rolling updates | `k8s/` (`maxSurge: 1`, `maxUnavailable: 0`), `scripts/deploy-local.sh` |
| Monitoring | `/metrics` -> Prometheus -> Grafana dashboard |
| Centralized logs | JSON logs -> Promtail -> Loki -> Grafana |
| Security checks | Bandit (code), pip-audit (dependencies), Trivy (image), non-root container |

## Structure
```
app/            Flask app (routes, db, metrics, web UI)
tests/          unit tests
k8s/            Kubernetes manifests
monitoring/     Prometheus, Promtail, Grafana provisioning
scripts/        deploy-local.sh, rollback.sh
Dockerfile, docker-compose.yml, VERSION, requirements*.txt
```

## 1. Run locally (no Docker) – quickest check
Needs Python 3.10+.
```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate        Linux/Mac:  source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v      # all 12 tests should pass
# run the app with demo data
# Windows PowerShell:  $env:SEED_DEMO="1"; python wsgi.py
# Linux/Mac:           SEED_DEMO=1 python wsgi.py
```
Open http://localhost:8000 (web UI), http://localhost:8000/health, http://localhost:8000/metrics.

## 2. Run with Docker Compose (app + monitoring + logging)
Needs Docker Desktop.
```bash
docker compose up -d --build
docker compose ps
```
| URL | What |
|---|---|
| http://localhost:8000 | Restaurant app |
| http://localhost:9090 | Prometheus (Status -> Targets should show `restaurant-app` UP) |
| http://localhost:3000 | Grafana (login `admin` / `admin`) -> Dashboards -> "Restaurant Management System" |

Create a few orders in the UI, then watch the request-rate panel and the log panel update.
Stop everything: `docker compose down` (add `-v` to wipe data).

## 3. Deploy to Kubernetes (minikube)
```bash
minikube start
./scripts/deploy-local.sh          # on Windows use Git Bash or WSL
kubectl -n restaurant port-forward svc/restaurant-service 8080:80
```
Open http://localhost:8080.

**Rolling update demo**
```bash
echo "1.1.0" > VERSION
./scripts/deploy-local.sh
kubectl -n restaurant rollout status deployment/restaurant-app
curl http://localhost:8080/health      # shows version 1.1.0 (re-run port-forward if it dropped)
```
**Rollback demo**
```bash
./scripts/rollback.sh
kubectl -n restaurant rollout history deployment/restaurant-app
```
Note: the app uses SQLite on a PersistentVolume, so keep `replicas: 1`. Scaling out would need a
shared database such as PostgreSQL (a good "future work" point for your report).

## 4. Git workflow
```bash
git init -b main
git add . && git commit -m "feat: initial Restaurant Management System"
git checkout -b develop
git checkout -b feature/menu-validation
# ...make a change...
git add . && git commit -m "feat: validate menu item price"
git checkout develop && git merge --no-ff feature/menu-validation
git checkout main && git merge --no-ff develop
git tag v1.0.0
```
Push to GitHub: create an empty repo, then
```bash
git remote add origin https://github.com/<you>/restaurant-management.git
git push -u origin main develop --tags
```
Open the **Actions** tab to see the pipeline: tests -> Bandit -> pip-audit -> Docker build ->
Trivy scan -> push to `ghcr.io/<you>/restaurant-management`.
Optional auto-deploy: set repo variable `ENABLE_DEPLOY=true` and secret `KUBE_CONFIG`
(base64 of your kubeconfig, for a cluster reachable from GitHub).

## 5. API quick reference
`GET/POST /api/restaurants`, `GET/PUT/DELETE /api/restaurants/<id>` – same pattern for
`/api/menu-items` and `/api/customers`. Orders: `GET/POST /api/orders`, `GET/DELETE /api/orders/<id>`,
`PATCH /api/orders/<id>/status`. Also `/api/stats`, `/health`, `/metrics`.
```bash
curl -X POST localhost:8000/api/orders -H "Content-Type: application/json" \
  -d '{"customer_id":1,"restaurant_id":1,"items":[{"menu_item_id":1,"quantity":2}]}'
```
(PowerShell: use the web UI, or `Invoke-RestMethod`.)

## 6. Troubleshooting
- **Port 8000/3000/9090 in use** – change the left side of the port mapping in `docker-compose.yml`.
- **Pod `ErrImagePull`** – the image was not loaded into the cluster; re-run `./scripts/deploy-local.sh`.
- **Promtail shows no logs on Windows** – make sure Docker Desktop uses the WSL2 backend.
- **Grafana log panel empty** – wait ~30 s after `docker compose up`, then generate some traffic.

## 7. Jenkins (alternative CI)
```bash
docker build -t jenkins-devops ./jenkins
MSYS_NO_PATHCONV=1 docker run -d --name jenkins -u root -p 8080:8080 -p 50000:50000 \
  -v jenkins_home:/var/jenkins_home -v /var/run/docker.sock:/var/run/docker.sock jenkins-devops
docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
```
Open http://localhost:8080, install suggested plugins, then create a *Pipeline* job:
Pipeline script from SCM -> Git -> your repo URL -> branch `*/main` -> Script Path `Jenkinsfile`.
Enable *Poll SCM* with `H/2 * * * *`, then click *Build Now*.
