-- Forwarded email (ING-01, ADR-039): one private inbound address per household. Looked up by its token when mail
-- arrives, before the household is known, so it isn't behind row-level security; it holds no health content.

CREATE TABLE app.inbound_addresses (
    token text PRIMARY KEY,
    household_id uuid NOT NULL UNIQUE REFERENCES app.households (id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, DELETE ON app.inbound_addresses TO {app};
