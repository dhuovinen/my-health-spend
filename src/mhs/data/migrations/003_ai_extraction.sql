-- Phase 1.3: AI extraction (ADR-028, ADR-034) is off for every household until an operator turns it on.

ALTER TABLE app.households ADD COLUMN ai_extraction boolean NOT NULL DEFAULT false;
