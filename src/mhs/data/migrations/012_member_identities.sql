-- Social sign-in (PRV-12, ADR-048): a member's Google or Microsoft account, linked by the provider's stable subject,
-- never by email. The email is only shown to the member, so they can tell which account is linked.

CREATE TABLE app.member_identities (
    provider text NOT NULL CHECK (provider IN ('google', 'microsoft')),
    subject text NOT NULL,
    member_id uuid NOT NULL REFERENCES app.members (id) ON DELETE CASCADE,
    email text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, subject),
    UNIQUE (member_id, provider)
);
GRANT SELECT, INSERT, DELETE ON app.member_identities TO {app};

-- Linking starts while signed in and finishes on a callback that can't read the session cookie, so the member is
-- recorded against the flow's state, in the same table as the other short-lived links.
ALTER TABLE app.enrolment_links DROP CONSTRAINT enrolment_links_purpose_check;
ALTER TABLE app.enrolment_links ADD CONSTRAINT enrolment_links_purpose_check
    CHECK (purpose IN ('enrol', 'recover', 'link_identity'));
