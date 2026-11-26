-- The landing page's waitlist (ADR-061): an address, the consent wording's version, and when. It belongs to no
-- household. The admin screen shows a count; mhs-admin lists and removes addresses.
CREATE TABLE app.waitlist (
    email text PRIMARY KEY,
    consent_version text NOT NULL,
    joined_at timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, DELETE ON app.waitlist TO {app};
