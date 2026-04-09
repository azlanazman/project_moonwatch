-- ---------------------------------------------------------------------------
-- PostgreSQL initialisation script for the OTel Learning Lab
--
-- Docker runs all *.sql files in /docker-entrypoint-initdb.d/ once,
-- the first time the data volume is created.
-- enterprise: equivalent to a Flyway V1__ or Liquibase baseline migration.
-- ---------------------------------------------------------------------------

-- Create the items table
CREATE TABLE IF NOT EXISTS items (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Seed data — gives the /items endpoint something to return immediately
-- without any manual inserts.
-- ---------------------------------------------------------------------------
INSERT INTO items (name, description) VALUES
    ('Prometheus',  'Metrics collection and alerting toolkit'),
    ('Grafana',     'Observability visualisation platform'),
    ('Loki',        'Log aggregation system, like Prometheus but for logs'),
    ('Tempo',       'Distributed tracing backend'),
    ('OTel Collector', 'Vendor-agnostic telemetry pipeline');
