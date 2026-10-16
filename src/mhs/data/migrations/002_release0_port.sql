-- Phase 1.2: owner-edit marks (ADR-011) and the import log, per household (ADR-032).

CREATE TABLE app.owner_edits (
    household_id uuid NOT NULL REFERENCES app.households (id) ON DELETE CASCADE,
    kind text NOT NULL,
    id text NOT NULL,
    edited_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (household_id, kind, id)
);
ALTER TABLE app.owner_edits ENABLE ROW LEVEL SECURITY;
CREATE POLICY household_only ON app.owner_edits
    USING (household_id = nullif(current_setting('mhs.household_id', true), '')::uuid)
    WITH CHECK (household_id = nullif(current_setting('mhs.household_id', true), '')::uuid);

CREATE TABLE app.imports (
    id bigserial PRIMARY KEY,
    household_id uuid NOT NULL REFERENCES app.households (id) ON DELETE CASCADE,
    imported_at timestamptz NOT NULL DEFAULT now(),
    source text NOT NULL,
    summary jsonb NOT NULL
);
CREATE INDEX imports_household ON app.imports (household_id, id DESC);
ALTER TABLE app.imports ENABLE ROW LEVEL SECURITY;
CREATE POLICY household_only ON app.imports
    USING (household_id = nullif(current_setting('mhs.household_id', true), '')::uuid)
    WITH CHECK (household_id = nullif(current_setting('mhs.household_id', true), '')::uuid);

GRANT SELECT, INSERT, UPDATE, DELETE ON app.owner_edits, app.imports TO {app};
GRANT USAGE ON SEQUENCE app.imports_id_seq TO {app};
