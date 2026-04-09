# ---------------------------------------------------------------------------
# Stage 1 – dependency install
# Using a separate stage keeps the final image lean by excluding pip cache.
# enterprise: multi-stage builds are standard in CI/CD pipelines to reduce
# image size and attack surface.
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# Copy only requirements first so Docker can cache this layer independently
# of source code changes — rebuilds are faster when only main.py changes.
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2 – runtime image
# ---------------------------------------------------------------------------
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Copy application source
COPY main.py .

# Expose the port uvicorn will listen on
EXPOSE 8000

# Install curl for the Docker healthcheck (slim image ships without it)
# Run as non-root for security best practice
# enterprise: production containers never run as root; many k8s policies block it.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --no-create-home appuser
USER appuser

# Start uvicorn
# --host 0.0.0.0 so the port is reachable from other containers / the host
# --reload is OFF here (production-style); use override for dev if needed
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
