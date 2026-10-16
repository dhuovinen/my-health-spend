-- Phase 1.1 Foundation (ADR-027, ADR-031). {app}, {worker} and {vault} are the tier roles.
-- Tables are owned by the migrating admin role, so row-level security applies to every tier role.

CREATE SCHEMA app;
CREATE SCHEMA vault;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA app TO {app}, {worker};
GRANT USAGE ON SCHEMA vault TO {vault};

-- Application tier: identity and tenancy. No health content here.
CREATE TABLE app.households (
    id uuid PRIMARY KEY,
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE app.household_keys (
    household_id uuid PRIMARY KEY REFERENCES app.households (id) ON DELETE CASCADE,
    wrapped bytea NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE app.members (
    id uuid PRIMARY KEY,
    household_id uuid NOT NULL REFERENCES app.households (id) ON DELETE CASCADE,
    email text NOT NULL,
    display_name text NOT NULL,
    password_hash text NOT NULL,
    totp_secret bytea NOT NULL,           -- sealed with the household data key
    totp_last_step bigint NOT NULL DEFAULT 0,
    failed_attempts integer NOT NULL DEFAULT 0,
    locked_until timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX members_email ON app.members (lower(email));
CREATE TABLE app.sessions (
    token_hash bytea PRIMARY KEY,         -- SHA-256 of the cookie value; the value itself is never stored
    member_id uuid NOT NULL REFERENCES app.members (id) ON DELETE CASCADE,
    household_id uuid NOT NULL REFERENCES app.households (id) ON DELETE CASCADE,
    mfa_passed boolean NOT NULL DEFAULT false,
    csrf_token text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now()
);

-- Records database (JSONB, as in Release 0's record store), one row per household, kind and id.
CREATE TABLE app.records (
    household_id uuid NOT NULL REFERENCES app.households (id) ON DELETE CASCADE,
    kind text NOT NULL,
    id text NOT NULL,
    data jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (household_id, kind, id)
);
ALTER TABLE app.records ENABLE ROW LEVEL SECURITY;
CREATE POLICY household_only ON app.records
    USING (household_id = nullif(current_setting('mhs.household_id', true), '')::uuid)
    WITH CHECK (household_id = nullif(current_setting('mhs.household_id', true), '')::uuid);

-- Job queue (ADR-027): the app enqueues for its household; the worker claims across households.
CREATE TABLE app.jobs (
    id bigserial PRIMARY KEY,
    household_id uuid NOT NULL REFERENCES app.households (id) ON DELETE CASCADE,
    kind text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{{}}',
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
    attempts integer NOT NULL DEFAULT 0,
    max_attempts integer NOT NULL DEFAULT 3,
    run_after timestamptz NOT NULL DEFAULT now(),
    locked_at timestamptz,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);
CREATE INDEX jobs_ready ON app.jobs (run_after, id) WHERE status = 'queued';
ALTER TABLE app.jobs ENABLE ROW LEVEL SECURITY;
CREATE POLICY app_household_only ON app.jobs TO {app}
    USING (household_id = nullif(current_setting('mhs.household_id', true), '')::uuid)
    WITH CHECK (household_id = nullif(current_setting('mhs.household_id', true), '')::uuid);
CREATE POLICY worker_claims_any ON app.jobs TO {worker} USING (true) WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON app.households, app.household_keys, app.members, app.sessions,
    app.records, app.jobs TO {app};
GRANT USAGE ON SEQUENCE app.jobs_id_seq TO {app};
GRANT SELECT, INSERT, UPDATE, DELETE ON app.records TO {worker};
GRANT SELECT, UPDATE ON app.jobs TO {worker};

-- Identity vault: its own schema, role and keys. Values are sealed with the vault's household data key.
CREATE TABLE vault.household_keys (
    household_id uuid PRIMARY KEY,
    wrapped bytea NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE vault.entries (
    household_id uuid NOT NULL,
    token text NOT NULL,
    kind text NOT NULL,
    lookup bytea NOT NULL,                -- keyed hash of the value, so the same value gets the same token
    sealed bytea NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (household_id, token),
    UNIQUE (household_id, kind, lookup)
);
ALTER TABLE vault.entries ENABLE ROW LEVEL SECURITY;
CREATE POLICY household_only ON vault.entries
    USING (household_id = nullif(current_setting('mhs.household_id', true), '')::uuid)
    WITH CHECK (household_id = nullif(current_setting('mhs.household_id', true), '')::uuid);
GRANT SELECT, INSERT, UPDATE, DELETE ON vault.household_keys, vault.entries TO {vault};
