# OTel Learning Lab

## Project Overview
Full-stack observability lab using OpenTelemetry.

## Stack
- Frontend: NGINX
- Backend: FastAPI (Python)
- Database: PostgreSQL
- Observability: OTel Collector, Prometheus, Loki, Tempo, Grafana

## Directory Structure
- app/frontend     → NGINX config
- app/backend      → FastAPI app
- app/database     → PostgreSQL init scripts
- observability/   → All OTel stack configs
- scripts/         → Helper scripts
- docs/            → Notes and diagrams

## Phases
1. App stack (NGINX + FastAPI + PostgreSQL)
2. OTel Collector
3. Metrics + Logs (Prometheus + Loki)
4. Traces (Tempo)
5. Dashboards + Alerts (Grafana)

## Common Commands
- Start everything: docker compose up -d
- View logs: docker compose logs -f [service]
- Stop: docker compose down
