-- Self-service sign-up with Google or Microsoft (PRV-13, ADR-059). A member who signed up has no password: they sign
-- in with the linked account, and recovery codes still lead to a new password (ADR-037).

ALTER TABLE app.members ALTER COLUMN password_hash DROP NOT NULL;
-- The provider the member signed up with; empty for a member created by mhs-admin.
ALTER TABLE app.members ADD COLUMN signed_up_with text NOT NULL DEFAULT '';
-- What the member agreed to when signing up, and when.
ALTER TABLE app.members ADD COLUMN terms_version text NOT NULL DEFAULT '';
ALTER TABLE app.members ADD COLUMN privacy_version text NOT NULL DEFAULT '';
ALTER TABLE app.members ADD COLUMN terms_accepted_at timestamptz;

-- Between the provider's callback and "Create account": who came back, for 15 minutes, under a hashed token. The
-- form token is checked as well as the cookie.
CREATE TABLE app.pending_signups (
    token_hash bytea PRIMARY KEY,
    provider text NOT NULL,
    subject text NOT NULL,
    email text NOT NULL,
    form_token text NOT NULL,
    expires_at timestamptz NOT NULL
);
GRANT SELECT, INSERT, DELETE ON app.pending_signups TO {app};
