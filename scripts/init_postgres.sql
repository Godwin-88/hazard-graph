-- Run once on first postgres container start
-- All table creation is handled by SQLAlchemy create_all()
-- This script creates extensions only

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Phone number encryption helper function
CREATE OR REPLACE FUNCTION encrypt_phone(phone TEXT) RETURNS TEXT AS $$
  SELECT encode(pgp_sym_encrypt(phone, current_setting('app.encryption_key', true)), 'base64');
$$ LANGUAGE SQL;

CREATE OR REPLACE FUNCTION decrypt_phone(encrypted TEXT) RETURNS TEXT AS $$
  SELECT pgp_sym_decrypt(decode(encrypted, 'base64'), current_setting('app.encryption_key', true));
$$ LANGUAGE SQL;