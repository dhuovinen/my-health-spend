-- Security log (PRV-09, ADR-025): account events without health content, kept for one year. No foreign key to the
-- household, so the record of a deletion outlives the household it describes.

CREATE TABLE app.security_log (
    id bigserial PRIMARY KEY,
    at timestamptz NOT NULL DEFAULT now(),
    household_id uuid,
    member_id uuid,
    event text NOT NULL CHECK (event ~ '^[a-z_]{{1,40}}$')
);
CREATE INDEX security_log_at ON app.security_log (at);
GRANT SELECT, INSERT, DELETE ON app.security_log TO {app};
GRANT USAGE ON SEQUENCE app.security_log_id_seq TO {app};
