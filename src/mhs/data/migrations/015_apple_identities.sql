-- Sign in with Apple (PRV-12, ADR-057): a third provider for linked accounts. Apple is asked for no email, so its
-- links keep the empty default.

ALTER TABLE app.member_identities DROP CONSTRAINT member_identities_provider_check;
ALTER TABLE app.member_identities ADD CONSTRAINT member_identities_provider_check
    CHECK (provider IN ('google', 'microsoft', 'apple'));
