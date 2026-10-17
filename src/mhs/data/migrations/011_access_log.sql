-- Access log (PRV-10, ADR-040): who viewed or changed which record of a household, and when. The application tier
-- can add entries and read them, never change or delete them; they go with the household when it is deleted.

CREATE TABLE app.access_log (
    id bigserial PRIMARY KEY,
    household_id uuid NOT NULL REFERENCES app.households (id) ON DELETE CASCADE,
    at timestamptz NOT NULL DEFAULT now(),
    member_id uuid,                       -- no foreign key: entries outlive a member who leaves
    action text NOT NULL CHECK (action IN ('view', 'download', 'create', 'change', 'delete', 'export')),
    kind text NOT NULL,
    record_id text NOT NULL
);
CREATE INDEX access_log_household ON app.access_log (household_id, id DESC);
ALTER TABLE app.access_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY household_only ON app.access_log
    USING (household_id = nullif(current_setting('mhs.household_id', true), '')::uuid)
    WITH CHECK (household_id = nullif(current_setting('mhs.household_id', true), '')::uuid);
GRANT SELECT, INSERT ON app.access_log TO {app};
GRANT USAGE ON SEQUENCE app.access_log_id_seq TO {app};
