"""
FastAPI backend for the OTel Learning Lab.

Routes:
  GET /health      → liveness probe (no DB dependency)
  GET /items       → list all items from PostgreSQL
  GET /items/{id}  → fetch a single item by ID

OTel instrumentation stubs are imported here but no-op until Phase 2,
when the OTel SDK is fully wired up. This mirrors the pattern used in
production services where instrumentation is added before the backend
is connected to a collector.
"""

import os
import psycopg2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="OTel Lab Backend", version="0.1.0")

# Allow NGINX (frontend) to call the backend from the browser
# enterprise: equivalent to configuring allowed origins in an API gateway
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tightened in later phases
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Database connection helper
# ---------------------------------------------------------------------------

def get_db_conn():
    """
    Opens a new psycopg2 connection per request.
    enterprise: in production this would be a connection pool (e.g. pgBouncer,
    SQLAlchemy pool, or asyncpg pool).
    """
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres"),
        port=int(os.getenv("DB_PORT", 5432)),
        dbname=os.getenv("DB_NAME", "otellab"),
        user=os.getenv("DB_USER", "otel"),
        password=os.getenv("DB_PASSWORD", "otelpass"),
    )

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    """
    Liveness probe — returns 200 immediately without touching the DB.
    Docker Compose and Kubernetes both hit this endpoint to decide if the
    container is healthy enough to receive traffic.
    """
    return {"status": "ok"}


@app.get("/items")
def list_items():
    """
    Returns all rows from the items table.
    enterprise: this is the kind of endpoint you'd add a RED metric to
    (Rate, Errors, Duration) in Phase 2 via OTel auto-instrumentation.
    """
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name, description, created_at FROM items ORDER BY id;")
        rows = cur.fetchall()
        return [
            {"id": r[0], "name": r[1], "description": r[2], "created_at": str(r[3])}
            for r in rows
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()


@app.get("/items/{item_id}")
def get_item(item_id: int):
    """
    Returns a single item by primary key.
    Raises 404 if the item does not exist.
    """
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, description, created_at FROM items WHERE id = %s;",
            (item_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
        return {"id": row[0], "name": row[1], "description": row[2], "created_at": str(row[3])}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()
