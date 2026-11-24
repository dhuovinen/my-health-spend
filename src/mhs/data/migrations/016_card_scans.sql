-- Insurance card scans (ING-11, ADR-059). A scan holds what was read from a card (identifiers as vault tokens)
-- and its images only while the member reviews it; both go when the scan is confirmed or abandoned, or after 24
-- hours. Images stay only if the owner's keep_card_images setting was on at confirmation ("kept"), linked to the plan.
-- The service settings table already holds the toggle, so this adds only the two tables and three functions.

CREATE TABLE app.card_scans (
    id text NOT NULL,
    household_id uuid NOT NULL REFERENCES app.households (id) ON DELETE CASCADE,
    created_by uuid,                      -- no foreign key: a scan outlives nothing, but a member may leave first
    created_at timestamptz NOT NULL DEFAULT now(),
    reading jsonb NOT NULL,               -- fields with confidences; member IDs, group numbers and names are tokens
    PRIMARY KEY (household_id, id)
);
ALTER TABLE app.card_scans ENABLE ROW LEVEL SECURITY;
CREATE POLICY household_only ON app.card_scans
    USING (household_id = nullif(current_setting('mhs.household_id', true), '')::uuid)
    WITH CHECK (household_id = nullif(current_setting('mhs.household_id', true), '')::uuid);
GRANT SELECT, INSERT, UPDATE, DELETE ON app.card_scans TO {app};

CREATE TABLE app.card_images (
    id text NOT NULL,
    household_id uuid NOT NULL REFERENCES app.households (id) ON DELETE CASCADE,
    scan_id text NOT NULL,
    side text NOT NULL CHECK (side IN ('front', 'back')),
    content_type text NOT NULL,
    object_key text NOT NULL,             -- sealed with the household's key, like an original
    sha256 text NOT NULL,
    state text NOT NULL DEFAULT 'review' CHECK (state IN ('review', 'kept')),
    plan_id text,                         -- set when kept
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (household_id, id)
);
ALTER TABLE app.card_images ENABLE ROW LEVEL SECURITY;
CREATE POLICY household_only ON app.card_images
    USING (household_id = nullif(current_setting('mhs.household_id', true), '')::uuid)
    WITH CHECK (household_id = nullif(current_setting('mhs.household_id', true), '')::uuid);
GRANT SELECT, INSERT, UPDATE, DELETE ON app.card_images TO {app};

-- Across households, counts and clean-up only (ADR-049: the admin screen shows counts, never household data). These
-- run as the table owner, so row-level security doesn't hide other households' rows from them.
CREATE FUNCTION app.card_image_counts() RETURNS TABLE (in_review bigint, kept bigint)
    LANGUAGE sql SECURITY DEFINER SET search_path = app, pg_temp AS
$$ SELECT count(*) FILTER (WHERE state = 'review'), count(*) FILTER (WHERE state = 'kept') FROM app.card_images $$;

-- Scans left open longer than the given hours: the scan and its images are removed; returns the object keys.
CREATE FUNCTION app.expire_card_scans(hours integer) RETURNS TABLE (object_key text)
    LANGUAGE sql SECURITY DEFINER SET search_path = app, pg_temp AS
$$
    WITH old AS (DELETE FROM app.card_scans WHERE created_at < now() - make_interval(hours => hours) RETURNING household_id, id)
    DELETE FROM app.card_images i USING old
        WHERE i.household_id = old.household_id AND i.scan_id = old.id AND i.state = 'review'
        RETURNING i.object_key
$$;

CREATE FUNCTION app.delete_kept_card_images() RETURNS TABLE (object_key text)
    LANGUAGE sql SECURITY DEFINER SET search_path = app, pg_temp AS
$$ DELETE FROM app.card_images WHERE state = 'kept' RETURNING object_key $$;

REVOKE ALL ON FUNCTION app.card_image_counts(), app.expire_card_scans(integer), app.delete_kept_card_images() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.card_image_counts(), app.expire_card_scans(integer), app.delete_kept_card_images() TO {app};
