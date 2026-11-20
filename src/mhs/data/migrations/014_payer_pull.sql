-- Insurer connection (ING-09, ADR-054): the member who started a pull is recorded against the flow's state, because
-- the payer's redirect back can't carry the SameSite=Strict session cookie. Single use, minutes long.

ALTER TABLE app.enrolment_links DROP CONSTRAINT enrolment_links_purpose_check;
ALTER TABLE app.enrolment_links ADD CONSTRAINT enrolment_links_purpose_check
    CHECK (purpose IN ('enrol', 'recover', 'link_identity', 'payer_pull'));
