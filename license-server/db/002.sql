BEGIN;
ALTER TABLE plans DROP CONSTRAINT IF EXISTS plans_amount_check;
ALTER TABLE plans ADD CONSTRAINT plans_amount_check CHECK(amount>=0);
INSERT INTO plans(id,name,amount,duration_days) VALUES
  ('trial','Dùng thử 1 ngày',0,1),('monthly','1 tháng (30 ngày)',50000,30)
ON CONFLICT(id) DO NOTHING;
CREATE TABLE IF NOT EXISTS auth_credentials (
  user_id uuid PRIMARY KEY REFERENCES users(id), password_hash text NOT NULL
);
CREATE TABLE IF NOT EXISTS administrator_accounts (
  user_id uuid PRIMARY KEY REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS trial_claims (
  user_id uuid PRIMARY KEY REFERENCES users(id), license_id uuid UNIQUE NOT NULL REFERENCES licenses(id),
  claimed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS trial_installations (
  installation_key text PRIMARY KEY, license_id uuid UNIQUE NOT NULL REFERENCES licenses(id),
  started_at timestamptz NOT NULL DEFAULT now()
);
COMMIT;
