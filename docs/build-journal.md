# OTel Learning Lab — Build Journal

> This file is a living document. Each phase appends its own section.
> Purpose: understand not just *what* was done, but *why* each decision was made
> and how it maps to real enterprise observability practice.

---

## Table of Contents

- [Environment Overview](#environment-overview)
- [Phase 1 — Build the App Stack](#phase-1--build-the-app-stack)
  - [Step 1: VM Setup & Bootstrap](#step-1-vm-setup--bootstrap)
  - [Step 2: Project Scaffold](#step-2-project-scaffold)
  - [Step 3: PostgreSQL — init.sql](#step-3-postgresql--initsql)
  - [Step 4: FastAPI Backend](#step-4-fastapi-backend)
  - [Step 5: NGINX Frontend](#step-5-nginx-frontend)
  - [Step 6: Docker Compose — wiring it all together](#step-6-docker-compose--wiring-it-all-together)
  - [Step 7: First Boot & Debugging](#step-7-first-boot--debugging)
  - [Step 8: Verification](#step-8-verification)
- [Key Concepts Glossary](#key-concepts-glossary)

---

## Environment Overview

| Item | Value |
|---|---|
| Host OS | Ubuntu 24.04 LTS (VMware VM) |
| VM IP | 172.16.0.50 |
| VM user | otel |
| Project directory (VM) | ~/otel-lab |
| Project directory (Mac) | ~/Library/CloudStorage/.../project_moonwatch |
| Container runtime | Docker Engine (docker-ce) + Compose plugin |

**Why VMware?**  
Running on a dedicated VM keeps your Mac clean and mirrors how most enterprise observability labs work — isolated, reproducible environments on a hypervisor or cloud instance.

---

## Phase 1 — Build the App Stack

**Goal:** `docker compose up` brings up NGINX, FastAPI, and PostgreSQL with no errors. Every service passes its healthcheck.

**Definition of Done:**
- `GET /api/health` returns `{"status": "ok"}`
- `GET /api/items` returns 5 rows from PostgreSQL
- `http://172.16.0.50` opens in a browser and shows the UI

---

### Step 1: VM Setup & Bootstrap

#### What happened

A bootstrap script was written to install three things on the Ubuntu VM:

1. **Docker Engine** (not Docker Desktop — this is the server-grade daemon)
2. **Git**
3. **Node.js 18** (available for later tooling if needed)

#### The bootstrap script explained

```bash
#!/bin/bash
set -e   # exit immediately on any error — prevents partial installs
```

**Installing Docker Engine (not Docker Desktop)**

```bash
# Step 1: create a directory for apt keyrings (package signing keys)
sudo install -m 0755 -d /etc/apt/keyrings

# Step 2: download Docker's GPG key and store it in the keyring directory
# This lets apt verify that Docker packages haven't been tampered with
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Step 3: add Docker's apt repository, scoped to the correct Ubuntu version
# $(dpkg --print-architecture) = amd64 on x86_64 VMs
# $(lsb_release -cs) = noble on Ubuntu 24.04
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu noble stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list

# Step 4: install Docker packages
# docker-ce            = the Docker daemon (server)
# docker-ce-cli        = the `docker` command-line tool
# containerd.io        = the low-level container runtime Docker sits on top of
# docker-buildx-plugin = BuildKit-based multi-platform image builder
# docker-compose-plugin = `docker compose` (v2, replaces standalone docker-compose)
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
```

**Why `docker-compose-plugin` and not `docker-compose`?**  
The standalone `docker-compose` (v1, Python) is deprecated. The plugin (`docker compose`) is v2, written in Go, and is the current standard. Commands use a space: `docker compose up` not `docker-compose up`.

**Adding the user to the docker group**

```bash
sudo usermod -aG docker $USER
# Requires logout/login to take effect.
# Without this, every docker command needs sudo.
# enterprise: in production, service accounts (not humans) run Docker,
# so group membership is managed via IAM or provisioning tools (Ansible, Terraform).
```

#### Key concept: SSH into a VM from Claude Code

Claude Code cannot open an interactive terminal over SSH (no pseudo-TTY). All SSH commands are run non-interactively:

```
ssh user@host "command to run"
```

`sudo` in non-interactive mode requires passwordless sudo OR piping the password via `-S`. This is why the bootstrap script had to be run from the VM console directly rather than from Claude Code.

---

### Step 2: Project Scaffold

#### Directory structure

```
otel-lab/
├── app/
│   ├── backend/        ← FastAPI Python source
│   ├── frontend/       ← NGINX config and static HTML
│   └── db/             ← PostgreSQL init SQL
├── otel/               ← OTel Collector (Phase 2)
├── grafana/
│   ├── dashboards/     ← Dashboard JSON (Phase 4)
│   └── provisioning/   ← Grafana datasource YAML (Phase 3)
├── docs/               ← This file lives here
├── .env.example        ← Template for secrets
├── docker-compose.yml  ← Single Compose file for the whole stack
└── CLAUDE.md           ← Instructions for AI assistant
```

**Why this structure?**  
Each top-level folder maps to a concern: `app/` is your application, `otel/` is your telemetry pipeline, `grafana/` is your visualisation layer. This separation means in Phase 5 you could hand the `otel/` folder to a platform team and the `app/` folder to a dev team — each folder is independently maintainable.

**enterprise equivalent:** This mirrors a mono-repo layout where platform and application teams share infrastructure-as-code but own separate directories.

#### How files were transferred to the VM

```bash
rsync -av --exclude='.git' --exclude='.DS_Store' \
  /path/to/project_moonwatch/ \
  otel@172.16.0.50:~/otel-lab/
```

**Why `rsync` over `scp`?**  
`rsync` is incremental — it only transfers files that have changed. On subsequent pushes (e.g. after editing a config), only the modified files are sent. `scp` copies everything every time. `rsync` also preserves timestamps and handles large directory trees cleanly.

`--exclude='.git'` prevents sending the full git history to the VM (unnecessary weight).

---

### Step 3: PostgreSQL — init.sql

**File:** `app/db/init.sql`

```sql
CREATE TABLE IF NOT EXISTS items (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

INSERT INTO items (name, description) VALUES
    ('Prometheus',     'Metrics collection and alerting toolkit'),
    ('Grafana',        'Observability visualisation platform'),
    ('Loki',           'Log aggregation system, like Prometheus but for logs'),
    ('Tempo',          'Distributed tracing backend'),
    ('OTel Collector', 'Vendor-agnostic telemetry pipeline');
```

#### How Docker runs init scripts

When the `postgres:15-alpine` container starts for the **first time**, it looks for files in `/docker-entrypoint-initdb.d/` and executes them in alphabetical order. In `docker-compose.yml` we mount:

```yaml
volumes:
  - ./app/db:/docker-entrypoint-initdb.d:ro
```

`:ro` = read-only mount. The container can read the SQL file but cannot modify it — a security good practice.

**Important:** Init scripts only run once — on the first boot when the data volume is empty. If you change `init.sql` and want to re-run it, you must destroy the volume:

```bash
docker compose down -v   # -v removes named volumes
docker compose up -d
```

**enterprise equivalent:** This is the same pattern as Flyway `V1__baseline.sql` or Liquibase `001_initial_schema.xml` — a versioned, idempotent migration that runs once.

#### Column type choices

| Column | Type | Reason |
|---|---|---|
| `id` | `SERIAL` | Auto-incrementing integer primary key |
| `name` | `VARCHAR(100)` | Bounded length, indexed efficiently |
| `description` | `TEXT` | Unbounded, no performance difference in Postgres |
| `created_at` | `TIMESTAMPTZ` | **With timezone** — always store timestamps with TZ in distributed systems to avoid ambiguity |

---

### Step 4: FastAPI Backend

#### File: `app/backend/requirements.txt`

```
fastapi==0.111.0           # web framework
uvicorn[standard]==0.29.0  # ASGI server
psycopg2-binary==2.9.9     # PostgreSQL driver
opentelemetry-sdk==1.24.0                         # OTel SDK core
opentelemetry-api==1.24.0                         # OTel API (no-op until Phase 2)
opentelemetry-instrumentation-fastapi==0.45b0     # auto-instrument HTTP spans
opentelemetry-instrumentation-psycopg2==0.45b0    # auto-instrument DB spans
opentelemetry-exporter-otlp==1.24.0               # send to OTel Collector
```

**Why install OTel packages now if they're not used yet?**  
Pinning all OTel packages to the same version at the start prevents version-skew bugs later. If you add them one at a time across multiple phases, subtle incompatibilities between `opentelemetry-api` and `opentelemetry-sdk` versions can cause silent data loss in traces. Install once, wire up later.

**Why `psycopg2-binary` not `psycopg2`?**  
`psycopg2-binary` ships with its own compiled `libpq` (PostgreSQL client library). Plain `psycopg2` requires `libpq-dev` to be installed in the OS — that's an extra `apt-get` step in the Dockerfile. The binary wheel trades a slightly larger package for a simpler build.

#### File: `app/backend/main.py`

**Application setup**

```python
app = FastAPI(title="OTel Lab Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)
```

`CORSMiddleware` lets the browser-loaded JavaScript (served by NGINX on port 80) call the backend API. Without it, the browser's Same-Origin Policy would block cross-origin requests. `allow_origins=["*"]` is permissive for a lab; in production you'd list exact origins.

**Database connection**

```python
def get_db_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres"),
        ...
    )
```

`os.getenv("DB_HOST", "postgres")` reads the value from an environment variable, falling back to `"postgres"` if not set. The hostname `postgres` resolves to the PostgreSQL container because they share the `app-net` Docker network — Docker's internal DNS maps the service name to the container IP automatically.

**Why a new connection per request?**  
This is intentionally simple for Phase 1. In production you'd use a connection pool (pgBouncer, SQLAlchemy's `pool_size`, or asyncpg). A pool reuses existing TCP connections to PostgreSQL instead of opening a new one on every request — much faster under load.

**Routes**

| Route | HTTP status | Notes |
|---|---|---|
| `GET /health` | 200 | No DB call — pure liveness check |
| `GET /items` | 200 | Queries all rows; 500 on DB error |
| `GET /items/{id}` | 200 / 404 | 404 if row missing; 500 on DB error |

**Why separate `/health` from `/items`?**  
A liveness probe should never depend on a downstream service. If PostgreSQL is slow, you don't want the healthcheck to fail — that would cause the orchestrator to restart the backend unnecessarily. The health endpoint just proves the process is alive. A separate `readiness` endpoint (not implemented yet) would check DB connectivity.

**enterprise pattern — RED metrics:**  
The `/items` endpoint is a canonical candidate for RED instrumentation in Phase 2:
- **R**ate — how many requests per second
- **E**rrors — what fraction return 5xx
- **D**uration — how long each request takes

#### File: `app/backend/Dockerfile`

```dockerfile
# Stage 1: install dependencies
FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: runtime image
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY main.py .
EXPOSE 8000
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --no-create-home appuser
USER appuser
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Why multi-stage build?**  
Stage 1 installs hundreds of Python packages including build tools (compilers, headers). Stage 2 copies only the installed packages, not the build tools. This keeps the final image smaller and reduces the CVE surface — fewer installed packages means fewer potential vulnerabilities.

**Why `--no-cache-dir`?**  
`pip` normally caches downloaded wheels in `~/.cache/pip`. In a Docker build that cache never gets reused (each `RUN` is a fresh layer), so it just wastes space. `--no-cache-dir` skips writing it.

**Why `--prefix=/install`?**  
Installing to `/install` in Stage 1 makes it easy to `COPY --from=builder /install /usr/local` into Stage 2 — a clean, explicit transfer of only the installed packages.

**The curl fix:**  
`python:3.11-slim` is a minimal Debian image that does not include `curl`. Our Docker healthcheck uses `curl -sf http://localhost:8000/health`. Without curl, the healthcheck command was not found and the container was permanently marked `unhealthy`. The fix: install `curl` in the Dockerfile with `--no-install-recommends` (skip optional packages) and clean up `apt` lists to keep the layer small.

**Why `USER appuser`?**  
Running as root inside a container means a container escape vulnerability gives the attacker root on the host. Running as a non-root user limits the blast radius. Many enterprise Kubernetes policies (`PodSecurityPolicy`, `OPA Gatekeeper`) will reject containers that run as root.

---

### Step 5: NGINX Frontend

#### File: `app/frontend/nginx.conf`

```nginx
upstream fastapi_backend {
    server backend:8000;
}
```

`upstream` declares a named backend pool. `backend` is the Docker service name — Docker DNS resolves it to the container's IP on `app-net`. Using an upstream block (rather than `proxy_pass http://backend:8000` inline) means you can add multiple backend instances here later for load balancing.

**Static files**

```nginx
location / {
    root  /usr/share/nginx/html;
    index index.html;
    try_files $uri $uri/ /index.html;
}
```

`try_files` tries the exact path first (`$uri`), then as a directory (`$uri/`), then falls back to `index.html`. This is the standard pattern for single-page apps — without it, refreshing a URL like `/items/3` would return a 404 from NGINX.

**API proxy**

```nginx
location /api/ {
    proxy_pass http://fastapi_backend/;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_pass_header traceparent;
    proxy_pass_header tracestate;
}
```

`/api/` on NGINX maps to `/` on the backend. So `GET /api/items` becomes `GET /items` when it reaches FastAPI. The trailing slash in both `location /api/` and `proxy_pass http://fastapi_backend/` is important — NGINX strips the `/api/` prefix before forwarding.

`X-Forwarded-For` preserves the original client IP through the proxy. Without it, every request to FastAPI appears to come from `127.0.0.1` (the NGINX container). Logging and rate-limiting depend on this.

`traceparent` / `tracestate` are **W3C TraceContext** headers — the standard way distributed tracing systems propagate trace IDs across service boundaries. Passing them through NGINX now means Phase 2 trace spans will be automatically linked end-to-end.

**Healthcheck endpoint**

```nginx
location /nginx-health {
    access_log off;
    return 200 "healthy\n";
    add_header Content-Type text/plain;
}
```

`access_log off` suppresses healthcheck hits from polluting access logs — in production, healthchecks fire every 5-15 seconds and create significant log noise if not suppressed.

#### File: `app/frontend/Dockerfile`

```dockerfile
FROM nginx:stable-alpine
COPY nginx.conf /etc/nginx/nginx.conf
COPY index.html /usr/share/nginx/html/index.html
EXPOSE 80
```

`nginx:stable-alpine` uses Alpine Linux (~5 MB base) vs Debian (~80 MB). The `CMD` is inherited from the base image (`nginx -g 'daemon off;'`), so no override is needed. `daemon off` keeps NGINX in the foreground — Docker requires the main process to stay in the foreground or the container exits.

---

### Step 6: Docker Compose — wiring it all together

**File:** `docker-compose.yml`

#### Networks

```yaml
networks:
  app-net:
    driver: bridge
  otel-net:
    driver: bridge
```

Two separate networks:

- **`app-net`** — application traffic: frontend ↔ backend ↔ postgres
- **`otel-net`** — observability traffic: backend → OTel Collector (Phase 2)

By joining the backend to `otel-net` now, Phase 2 only needs to add the Collector service — no changes to the backend service definition.

**enterprise equivalent:** This mirrors network segmentation in enterprise environments — management/telemetry traffic on a separate VLAN or subnet from application traffic.

#### Service: postgres

```yaml
postgres:
  image: postgres:15-alpine
  environment:
    POSTGRES_DB:       ${DB_NAME:-otellab}
    POSTGRES_USER:     ${DB_USER:-otel}
    POSTGRES_PASSWORD: ${DB_PASSWORD:-otelpass}
  volumes:
    - postgres_data:/var/lib/postgresql/data     # persist data
    - ./app/db:/docker-entrypoint-initdb.d:ro    # seed on first boot
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U ${DB_USER:-otel} -d ${DB_NAME:-otellab}"]
    interval: 10s
    timeout: 5s
    retries: 5
    start_period: 10s
```

`${DB_NAME:-otellab}` reads from the `.env` file (or environment), falling back to `otellab` if not set. This pattern avoids hardcoded credentials in `docker-compose.yml`.

`pg_isready` is the canonical PostgreSQL readiness check — it speaks the PostgreSQL wire protocol and confirms the server is accepting connections before the backend tries to connect.

`start_period: 10s` — Docker doesn't count failures during this window. PostgreSQL takes a few seconds to initialise on first boot (running `init.sql`); without `start_period`, early failures would count against `retries` and potentially mark the container unhealthy before it's finished starting.

#### Service: backend

```yaml
backend:
  build:
    context: ./app/backend
  depends_on:
    postgres:
      condition: service_healthy
```

`condition: service_healthy` is the key line. Without it, `depends_on` only waits for the container to *start*, not for it to be *ready*. With it, Docker Compose holds the backend container at the `Starting` state until postgres passes its healthcheck. This eliminates a whole class of race-condition startup bugs.

#### Service: frontend

```yaml
frontend:
  ports:
    - "80:80"
  depends_on:
    backend:
      condition: service_healthy
```

Only the frontend exposes a port to the host (`80:80`). The backend and postgres are internal — they're only reachable from other containers on the shared network. This is the correct security posture: one entry point, everything else internal.

**enterprise equivalent:** In Kubernetes this maps to having one `LoadBalancer` Service (NGINX) while backend and postgres use `ClusterIP` Services (internal only).

#### Environment variable pattern: `.env` + `.env.example`

```
.env.example   ← committed to git (template, no real values)
.env           ← gitignored (real values, never committed)
```

`docker compose` automatically reads `.env` from the project root. Variables defined there override the `:-default` fallbacks in `docker-compose.yml`.

**enterprise equivalent:** `.env.example` is your "contract" — it documents what variables the app needs. In production the actual values come from a secrets manager (Vault, AWS Secrets Manager, k8s Secrets).

---

### Step 7: First Boot & Debugging

#### Problem encountered: backend healthcheck failing

After the first `docker compose up --build -d`, postgres came up healthy but the backend was stuck in `(unhealthy)` state.

**Diagnosis:**

```bash
docker inspect otellab-backend --format='{{json .State.Health}}'
```

Output:
```json
{"Status":"unhealthy","Log":[{"Output":"/bin/sh: 1: curl: not found\n"}]}
```

**Root cause:** The healthcheck command in `docker-compose.yml` uses `curl`:

```yaml
test: ["CMD-SHELL", "curl -sf http://localhost:8000/health || exit 1"]
```

`python:3.11-slim` is a minimal image that does not ship with `curl`. The command was not found, so the check always failed.

**Fix:** Add `curl` installation to the backend Dockerfile:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --no-create-home appuser
```

`--no-install-recommends` skips optional packages (documentation, locale files, etc.) that would add ~10 MB for no benefit in a container.  
`rm -rf /var/lib/apt/lists/*` deletes the apt package index after install — it's only needed during `apt-get install` and would otherwise inflate every derived image layer.

**Because the frontend `depends_on` the backend with `condition: service_healthy`, the frontend never started during this failure** — it stayed in `Waiting` state. This is exactly the intended behaviour: you don't want NGINX serving an unhealthy backend. The dependency chain worked correctly.

#### Startup sequence

```
postgres starts
  → postgres init.sql runs (creates table, inserts 5 rows)
    → postgres healthcheck passes
      → backend starts (postgres is ready)
        → backend healthcheck passes
          → frontend starts (backend is ready)
            → frontend healthcheck passes
              → stack is fully up
```

This chain is enforced by `depends_on: condition: service_healthy` at each step.

---

### Step 8: Verification

```bash
# Health check
curl http://172.16.0.50/api/health
# → {"status":"ok"}

# Items from database
curl http://172.16.0.50/api/items
# → [{"id":1,"name":"Prometheus",...}, ...]

# Single item
curl http://172.16.0.50/api/items/1
# → {"id":1,"name":"Prometheus","description":"Metrics collection and alerting toolkit",...}

# NGINX direct health
curl http://172.16.0.50/nginx-health
# → healthy

# Container status
docker compose ps
# NAME               STATUS
# otellab-postgres   Up (healthy)
# otellab-backend    Up (healthy)
# otellab-frontend   Up (healthy)
```

**Request flow for `GET /api/items`:**

```
Browser
  → GET /api/items
    → NGINX (port 80)
      strips /api/ prefix
      → forwards GET /items to backend:8000
        → FastAPI /items handler
          → psycopg2 connects to postgres:5432
            → SELECT * FROM items
          ← 5 rows returned
        ← JSON response
      ← proxied back through NGINX
    ← HTTP 200 JSON
  ← rendered in browser
```

---

## Key Concepts Glossary

| Term | What it means in this project |
|---|---|
| **ASGI** | Async Server Gateway Interface — the Python standard that FastAPI and uvicorn speak. Like WSGI but supports async/websockets. |
| **Bridge network** | Docker's default network mode. Containers on the same bridge can reach each other by service name. Isolated from other bridges. |
| **CORS** | Cross-Origin Resource Sharing. Browser security policy that blocks JavaScript from calling APIs on a different origin. Middleware must explicitly allow it. |
| **depends_on** | Docker Compose directive. `condition: service_healthy` waits for a passing healthcheck, not just container start. |
| **healthcheck** | A command Docker runs periodically inside a container. Exit 0 = healthy, non-zero = unhealthy. Orchestrators use this to route traffic. |
| **init.sql** | SQL files in `/docker-entrypoint-initdb.d/` run once on first Postgres boot. Equivalent to a baseline database migration. |
| **liveness probe** | Checks if a process is alive. If it fails, the orchestrator restarts the container. Should never call external dependencies. |
| **multi-stage build** | Dockerfile pattern: Stage 1 builds/installs, Stage 2 copies only the output. Produces smaller, cleaner final images. |
| **named volume** | A Docker-managed storage volume (`postgres_data`). Persists across `docker compose down` unless explicitly deleted with `-v`. |
| **OTel** | OpenTelemetry. A vendor-neutral standard for collecting traces, metrics, and logs. Replaces proprietary agents. |
| **OTLP** | OpenTelemetry Line Protocol. The wire format (gRPC or HTTP) used to send telemetry from an app to a Collector. |
| **readiness probe** | Checks if a service is ready to accept traffic. A service can be alive (liveness OK) but not yet ready (e.g. still warming up cache). |
| **RED metrics** | Rate, Errors, Duration — the three metrics that describe the health of any request-driven service. |
| **rsync** | File sync tool. Sends only changed files (incremental). Preferred over `scp` for directory transfers. |
| **TraceContext (W3C)** | HTTP header standard (`traceparent`, `tracestate`) for propagating trace IDs across service boundaries. |
| **upstream (NGINX)** | A named pool of backend servers. Enables load balancing by listing multiple `server` entries. |

---

*Phase 2 content will be added here after OTel Collector instrumentation is complete.*
