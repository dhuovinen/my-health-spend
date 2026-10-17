-- Self-service account recovery (TC-PRV-07-3, ADR-037): single-use recovery codes, and recovery links that are
-- their own kind, so an enrolment link can't be used to change a password.

CREATE TABLE app.recovery_codes (
    member_id uuid NOT NULL REFERENCES app.members (id) ON DELETE CASCADE,
    code_hash bytea NOT NULL,             -- SHA-256 of the normalized code; the code itself is never stored
    used_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (member_id, code_hash)
);
GRANT SELECT, INSERT, UPDATE, DELETE ON app.recovery_codes TO {app};

ALTER TABLE app.enrolment_links ADD COLUMN purpose text NOT NULL DEFAULT 'enrol' CHECK (purpose IN ('enrol', 'recover'));
