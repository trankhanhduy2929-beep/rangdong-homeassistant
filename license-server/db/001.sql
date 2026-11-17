BEGIN;
CREATE TABLE IF NOT EXISTS users (
  id uuid PRIMARY KEY, email text UNIQUE NOT NULL, phone text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS email_codes (
  email text PRIMARY KEY, digest text NOT NULL, expires_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  digest text PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id),
  expires_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS rate_limits (
  key text PRIMARY KEY, count integer NOT NULL, resets_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS plans (
  id text PRIMARY KEY, name text NOT NULL, amount integer NOT NULL CHECK(amount > 0),
  duration_days integer CHECK(duration_days > 0), active boolean NOT NULL DEFAULT true
);
INSERT INTO plans(id,name,amount) VALUES ('lifetime','Vĩnh viễn',200000)
ON CONFLICT(id) DO NOTHING;
CREATE SEQUENCE IF NOT EXISTS order_code_seq START 1000000000;
CREATE TABLE IF NOT EXISTS orders (
  id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id),
  plan_id text NOT NULL REFERENCES plans(id), amount integer NOT NULL CHECK(amount > 0),
  duration_days integer, order_code bigint UNIQUE NOT NULL DEFAULT nextval('order_code_seq'),
  request_id uuid NOT NULL, status text NOT NULL DEFAULT 'pending'
    CHECK(status IN ('pending','paid','cancelled','expired')),
  payment_link_id text UNIQUE, checkout_url text, qr_code text,
  created_at timestamptz NOT NULL DEFAULT now(), paid_at timestamptz,
  UNIQUE(user_id,request_id)
);
CREATE TABLE IF NOT EXISTS licenses (
  id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id),
  plan_id text NOT NULL REFERENCES plans(id), order_id uuid UNIQUE REFERENCES orders(id),
  key_hash text UNIQUE NOT NULL, key_cipher text NOT NULL,
  status text NOT NULL DEFAULT 'active' CHECK(status IN ('active','locked','revoked')),
  expires_at timestamptz, installation_key text, generation integer NOT NULL DEFAULT 1,
  manual_request_id uuid UNIQUE, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS activations (
  license_id uuid NOT NULL REFERENCES licenses(id),
  component text NOT NULL CHECK(component IN ('addon','custom')),
  client_id uuid NOT NULL, last_seen timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(license_id,component)
);
CREATE TABLE IF NOT EXISTS license_nonces (
  digest text PRIMARY KEY, expires_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS payments (
  reference text PRIMARY KEY, order_id uuid NOT NULL REFERENCES orders(id),
  payment_link_id text NOT NULL, amount integer NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS audit_log (
  id uuid PRIMARY KEY, actor_id uuid REFERENCES users(id), action text NOT NULL,
  target_id uuid, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS orders_user_created ON orders(user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS licenses_user_created ON licenses(user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS nonces_expiry ON license_nonces(expires_at);
COMMIT;
