-- Import previews held between "Check" and "Confirm" (ADR-036), so any app instance can confirm them.
-- Sealed with the household's data key: a preview can hold attached statements.

CREATE TABLE app.import_previews (
    household_id uuid NOT NULL REFERENCES app.households (id) ON DELETE CASCADE,
    token text NOT NULL,
    sealed bytea NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (household_id, token)
);
ALTER TABLE app.import_previews ENABLE ROW LEVEL SECURITY;
CREATE POLICY household_only ON app.import_previews
    USING (household_id = nullif(current_setting('mhs.household_id', true), '')::uuid)
    WITH CHECK (household_id = nullif(current_setting('mhs.household_id', true), '')::uuid);
GRANT SELECT, INSERT, DELETE ON app.import_previews TO {app};
