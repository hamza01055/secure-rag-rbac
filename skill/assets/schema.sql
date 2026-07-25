-- Secure RAG with RBAC — relational source of truth.
-- The vector store holds chunks and labels; this holds identity and metadata.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE tenants (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE roles (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name             TEXT NOT NULL,
    clearance_level  INT  NOT NULL CHECK (clearance_level BETWEEN 0 AND 100),
    description      TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, name)
);

CREATE TABLE users (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email            CITEXT NOT NULL,
    hashed_password  TEXT NOT NULL,
    role_id          UUID NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, email)
);
CREATE INDEX users_role_idx ON users(role_id);

-- ON DELETE RESTRICT on role_id is deliberate: deleting a role that users still
-- hold would otherwise orphan them, and an orphaned user is a user whose filter
-- cannot be built. Reassign first, then delete.

CREATE TABLE documents (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    filename      TEXT NOT NULL,
    storage_key   TEXT NOT NULL,
    uploaded_by   UUID NOT NULL REFERENCES users(id),
    min_clearance INT  NOT NULL CHECK (min_clearance BETWEEN 0 AND 100),
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','indexing','indexed','failed','deleting')),
    chunk_count   INT  NOT NULL DEFAULT 0,
    indexed_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX documents_tenant_status_idx ON documents(tenant_id, status);

-- Explicit allowlist, alongside the numeric clearance threshold. Both are
-- mirrored into every vector point's payload at ingest time.
CREATE TABLE document_roles (
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    role_id     UUID NOT NULL REFERENCES roles(id)     ON DELETE CASCADE,
    PRIMARY KEY (document_id, role_id)
);

-- A document with no rows here would be unreachable by anyone, which is safe
-- but almost always a mistake. Enforce at least one role in the application,
-- and audit for violations:
--   SELECT d.id FROM documents d LEFT JOIN document_roles dr ON dr.document_id = d.id
--   WHERE dr.document_id IS NULL;

CREATE TABLE audit_log (
    id           BIGSERIAL PRIMARY KEY,
    tenant_id    UUID NOT NULL,
    user_id      UUID NOT NULL,
    role_name    TEXT NOT NULL,
    query        TEXT NOT NULL,
    chunk_ids    TEXT[] NOT NULL DEFAULT '{}',   -- ids only, never chunk text
    returned     INT  NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX audit_user_time_idx ON audit_log(user_id, created_at DESC);

-- Seed data for local development and for the leak tests in
-- scripts/verify_rbac.py. Passwords are placeholders — replace before any
-- deployment, and never commit real hashes.
INSERT INTO tenants (id, name) VALUES
  ('11111111-1111-1111-1111-111111111111', 'acme');

INSERT INTO roles (tenant_id, name, clearance_level) VALUES
  ('11111111-1111-1111-1111-111111111111', 'Admin',       100),
  ('11111111-1111-1111-1111-111111111111', 'HR',           60),
  ('11111111-1111-1111-1111-111111111111', 'Engineering',  40),
  ('11111111-1111-1111-1111-111111111111', 'Intern',       10);
