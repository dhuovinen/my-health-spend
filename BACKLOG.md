# BACKLOG

Items deferred from the MVP. Newest decisions are in `docs/MVP_REQUIREMENTS.md` section 9.

| ID | Item | Origin | Notes |
| --- | --- | --- | --- |
| B-1 | Automatic extraction from PDFs/images into the ingest JSON, with a confirm step | Plan phase 2 | Raises ND-9 if an outside OCR/AI service is used. |
| B-2 | Agreed rate from provider billing | Owner, 2026-10-09 | Review whether bills reliably show a rate (`rate` field already in the bill line) and how it compares to the EOB `allowed`. |
| B-3 | Supplements and equipment: HSA/FSA eligibility, and member-submitted claims to insurance that may count toward the deductible | Owner, 2026-10-09 | Unknown whether insurers accept these or whether it varies by plan. Needs research before modelling. |
| B-4 | Ledger over time: chart of charges, payments and running balance per provider and overall | Owner, 2026-10-09 | MVP has the ledger table only. |
| B-5 | Confirmed HSA/FSA eligibility rules (replace "possible opportunity" with eligible / not eligible / needs a letter of medical necessity) | Owner, 2026-10-09 | MVP flags every non-HSA payment as a possibility. |
| B-6 | In-app forms to add and edit visits and documents | Review | MVP corrects data by re-importing JSON. |
| B-7 | Pre-visit strategy (use case 2): self-pay vs insurance, account choice, expected cost | Plan phase 5 | Depends on open question: does self-pay count toward the deductible? |
| B-8 | Service-line (CPT) reconciliation | Review | Lines are captured on EOBs but not checked. |
| B-9 | Help/documentation content | Owner | Done 2026-10-17 (branch feat/r1-help): statuses, checks, uploads, recovery, import, Settings, your data. |
| B-10 | Settings: data export, backup, delete all; configurable "waiting" threshold; FSA rules | Owner / review | Stub sections in MVP. |
| B-11 | Provider network status that changes by plan year | Review | MVP keeps one status per provider. |
| B-12 | Bill and EOB revision history (corrected EOBs, reissued bills) | Review | MVP keeps the latest; notes capture history. |
| B-13 | Account connections (HSA, insurer, card) | Plan | See ND-13. |
| B-14 | Import claims for other household members | Plan | Members and member-provider links are in the MVP model (D9); the claims export so far covers the owner only. |
| B-15 | Generalize the ingest schema into a baseline for all scenarios | Owner, 2026-10-09 | Use `extensions` to trial new fields; promote and bump `schema_version`. |
| B-16 | Deferred NFRs ND-1 to ND-14 | Owner, 2026-10-09 | Trigger: anyone other than the owner uses the app. |
| B-17 | Account fee flags (e.g. HSA paper-statement fees) as savings opportunities | Real data, 2026-10-09 | $1/month paper statement fee seen on the HSA. |
| B-18 | Importers for other insurers and HSA providers | Real data, 2026-10-09 | `tools/build_ingest.py` handles one claims CSV layout and one HSA export layout. |
| B-19 | HSA contribution tracking against the annual IRS limit | Real data, 2026-10-09 | Contributions are now imported as `account_transaction`. |
| B-20 | Statement parsers for other provider billing systems | Real data, 2026-10-09 | One layout supported (Southeastern Retina). |
| B-21 | Prior-year (2025) HSA history | Real data, 2026-10-09 | Needed to close 2025 Southeastern Retina payments; HSA export starts 2026-01-14. |
| B-22 | Follow-up tracking on provider notes (open / resolved, follow-up date, reminders) | Owner, 2026-10-09 | MVP notes are a plain dated log. |
