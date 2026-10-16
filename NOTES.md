# NOTES

## What this is

My Health Spend (MH$): a personal app that reconciles provider bills, insurer EOBs and payment
records (HSA/FSA/card) per visit to find billing errors and overpayment. Release 0 (built) is
single-user and local; Release 1 is a server-side web app for the household. The project is now
durable tier: see `CLAUDE.md` (runbook, gotchas) and `docs/` (VISION, ARCHITECTURE, ROADMAP,
DECISIONS, TESTING, SETUP, the Product Requirements, MVP_REQUIREMENTS and TEST_PLAN).

## How to run

See `CLAUDE.md` ("How to run") and `docs/SETUP.md`.

## Status

2026-10-09: MVP requirements agreed (`MVP_REQUIREMENTS.md`), backlog started (`BACKLOG.md`),
ingest schema v0.1 and a made-up sample file written and validated. Local web app chosen; framework
not yet picked. No app code yet. Waiting on the owner's real sample visits.
2026-10-09: Real 2026 claims (11) and HSA history (77 rows) converted to `data/ingest-2026.json`.
2026-10-09: Added 7 Southeastern Retina statements (2025-10 to 2026-10), household members and
provider relationships. Ingest now 15 visits, 96 documents.
2026-10-09: MVP app built: hero, visits, visit detail, provider ledgers, import, settings (plans,
limits, members, accounts, providers, provider matches), help stub. 22 tests passing. Real 2026 data imported.
2026-10-09: Provider notes (dated contact log per provider, linked to a visit) on branch feat/provider-notes.
2026-10-15: Full product requirements written; product docs moved into `docs/`.
2026-10-15: Test plan written (326 cases). Owner decisions applied to PRD (Release 0/1 split, HSA first,
server-side data, status order, money identities, tolerance, owner edits win). Re-import now keeps
in-app edits unless replaced. Release 0 gaps closed: C6 balance age and second notice, HR-4 counts
with links (32 tests passing). Records deleted in the app also stay deleted on re-import. Statements accept an optional `notice` field (schema still 0.1).
2026-10-15: Release 1 planning started. Scope set (49 requirements: lean core, household, Release 0
carry-over; responsive web; payments split by statement, else oldest first). Project moved to durable
tier: VISION, ARCHITECTURE, ROADMAP, DECISIONS (ADR-001 to 028), TESTING, SETUP, CLAUDE.md.
2026-10-15: ADR-021 to 028 and all ambiguity definitions accepted and written into the PRD; no
Release 1 test case is blocked. Still open for phase 1.0: hosting, OCR approach, test environment,
merge and tag Release 0.
2026-10-15: Release 0 merged into main (075f187) and tagged release-0.
2026-10-16: Phase 1.0 done: OCR is PDF text layer then Document AI with Presidio scrubbing (ADR-029);
build locally on Docker Compose, production on Google Cloud (ADR-030); test environment defined.
Next: phase 1.1 Foundation on branch work off main.
