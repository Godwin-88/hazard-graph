-- HazardGraph — PostgreSQL Schema Initialisation
-- Run once on first postgres container start.
-- Tables are created by SQLAlchemy create_all() but this script
-- ensures the schema exists for CI/CD and fresh deployments.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Phone number encryption helper function
CREATE OR REPLACE FUNCTION encrypt_phone(phone TEXT) RETURNS TEXT AS $$
  SELECT encode(pgp_sym_encrypt(phone, current_setting('app.encryption_key', true)), 'base64');
$$ LANGUAGE SQL;

CREATE OR REPLACE FUNCTION decrypt_phone(encrypted TEXT) RETURNS TEXT AS $$
  SELECT pgp_sym_decrypt(decode(encrypted, 'base64'), current_setting('app.encryption_key', true));
$$ LANGUAGE SQL;

-- Users table (created by SQLAlchemy, but defined here for CI/CD fallback)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'viewer',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    preferred_language VARCHAR(10) NOT NULL DEFAULT 'en',
    phone VARCHAR(50),
    region_focus VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);
CREATE INDEX IF NOT EXISTS ix_users_username ON users(username);
CREATE INDEX IF NOT EXISTS ix_users_role ON users(role);

-- Seed default admin user (password: HazardGraph2026!)
INSERT INTO users (username, email, hashed_password, name, role, is_active, preferred_language, created_at, updated_at)
VALUES (
    'admin',
    'admin@hazardgraph.io',
    '$2b$12$LJ3m4ys3Lk0TSwHnbfOMiOXPm1Q8pKJhPnqFgGzpGzpYzGzpzGzpG',
    'Admin User',
    'admin',
    TRUE,
    'en',
    NOW(),
    NOW()
) ON CONFLICT (email) DO NOTHING;
