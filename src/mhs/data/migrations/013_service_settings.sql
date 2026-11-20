-- Admin screen and an owner-controlled authenticator (PLT-09, ADR-049). Settings for the whole service, owners,
-- and what the sign-in needs to know to make the code optional and bring it back safely.

CREATE TABLE app.service_settings (
    name text PRIMARY KEY CHECK (name ~ '^[a-z_]{{1,30}}$'),
    value boolean NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by uuid                       -- the owner; no foreign key, so the setting outlives a deleted member
);
GRANT SELECT, INSERT, UPDATE ON app.service_settings TO {app};

-- An owner can open the admin screen and always signs in with the code.
ALTER TABLE app.members ADD COLUMN is_owner boolean NOT NULL DEFAULT false;
-- The member has entered a code from their authenticator at least once.
ALTER TABLE app.members ADD COLUMN totp_confirmed boolean NOT NULL DEFAULT false;
UPDATE app.members SET totp_confirmed = true WHERE totp_last_step > 0;
-- The member has signed in without a code, so when the code comes back they may be shown their authenticator.
ALTER TABLE app.members ADD COLUMN signed_in_without_code boolean NOT NULL DEFAULT false;

-- Whether the session entered a code; turning the code back on ends the sessions that didn't.
ALTER TABLE app.sessions ADD COLUMN code_passed boolean NOT NULL DEFAULT false;
UPDATE app.sessions SET code_passed = mfa_passed;
