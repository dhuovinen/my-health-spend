-- Single-use links that show a member's authenticator QR code once (PRV-11; docs/DEMO.md). The app tier
-- decrypts the member's TOTP secret when the link is opened; the link is deleted as it is used.

CREATE TABLE app.enrolment_links (
    token_hash bytea PRIMARY KEY,         -- SHA-256 of the link token; the token itself is never stored
    member_id uuid NOT NULL REFERENCES app.members (id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, DELETE ON app.enrolment_links TO {app};
