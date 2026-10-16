# Roadmap

**Current phase: 1.0, Release 1 planning.**

Requirement IDs refer to the [Product Requirements](<My Health Spend (MHS) Product Requirements.md>). Test cases for each are in [TEST_PLAN.md](TEST_PLAN.md).

## Release 0: local MVP (done)

Built Oct 9 to 15, 2026 from [MVP_REQUIREMENTS.md](MVP_REQUIREMENTS.md). A single-owner laptop app: JSON import from a converter, the reconciliation checks C1 to C8, visit list and detail, provider ledgers and notes, plan-limit progress, HSA flags with counts, and Settings. Re-import keeps edits made in the app. 32 automated tests; core coverage 96%.

| Item | Status |
| --- | --- |
| All MVP requirements built | Done (C6 aging and HR-4 counts closed 2026-10-15) |
| Merge `feat/provider-notes` into `main` and tag `release-0` | **To do** (owner's go-ahead) |
| Owner data still to load | 2026 dental and 2025 UMR plan limits; 2025 HSA history (B-21) |

## Release 1: server-side web app for the household

49 requirements: lean core, household, and Release 0 carried over ([PRD Release 1 scope](<My Health Spend (MHS) Product Requirements.md#release-1-scope>), ADR-018).

| Phase | Goal | Requirements | Exit |
| --- | --- | --- | --- |
| **1.0 Planning** (current) | Settle what is still open and set up for the build | none | ~~ADRs 021 to 028 and ambiguity definitions accepted~~ (done 2026-10-15); hosting chosen; OCR approach chosen; test environment defined; Release 0 merged and tagged |
| 1.1 Foundation | A secure, empty server app the household can sign in to | PRV-11, PRV-06, PRV-07, PRV-08, PLT-06 | MFA sign-in; household isolation tests pass (TC-PRV-11-*); encrypted storage and a tested restore; CI runs the scenario library |
| 1.2 Port Release 0 | Everything Release 0 does, on the server, for a household | MAT-02, MAT-03, MAT-04, MAT-07, MAT-09, ALC-03, ALC-04, ALC-06, REC-07, REC-08, TAX-04, DSP-03, UX-03, UX-04, UX-05, ING-08, ING-10 | Owner's Release 0 data migrated through the JSON admin import; Appendix A regression suite green on the server |
| 1.3 Ingestion and privacy pipeline | Upload a photo or PDF and get confirmed, pseudonymized data | ING-01, ING-02, ING-03, ING-04, ING-05, ING-07, PRV-01, PRV-02, PRV-03, PRV-04, PLT-04 | Extraction corpus meets the accuracy target; outbound capture finds no identifiers (TC-PRV-01-1, TC-PLT-04-1) |
| 1.4 Matching and reconciliation | Line-level matching and the three money identities | MAT-01, MAT-05, MAT-06, MAT-10, REC-01, REC-02, REC-03, REC-04, REC-05, REC-11, REC-13, ALC-01 | All P1 REC and MAT cases pass; nine statuses live |
| 1.5 Web experience | Visit cards and detail on phone and desktop, household view | UX-01, UX-02, UX-06, UX-10 | UX cases pass at 375px and 1280px |
| 1.6 Hardening and acceptance | Prove it on real visits | none new | Full P1 test pass; owner reconciles a month of real household visits; false-positive rate measured |

**Launch gate for anyone outside the owner's household:** CMP-01 to CMP-04 (breach response, consent, privacy policy, disclaimers) and PRV-09 (export and delete), plus a review by a healthcare privacy attorney.

## Release 2

The 47 P2 requirements, grouped:

| Theme | Requirements |
| --- | --- |
| Accuracy and trust | MAT-08 claim versions, REC-06 cost-sharing checks, REC-09 denial codes, REC-10 tolerance, PLT-01 reference tables, PLT-02 accuracy targets, PLT-03 traceability, ING-06 learning from corrections |
| Money detail | ALC-02 payment sources, ALC-05 secondary insurance, ALC-07 visual breakdown, ALC-08 refunds, REC-12 self-pay vs negotiated |
| HSA and tax | TAX-01, TAX-02, TAX-03, TAX-06 to TAX-10 |
| Disputes | DSP-01, DSP-02, DSP-04, DSP-05, DSP-07 |
| Pre-visit strategy | PRE-01, PRE-02, PRE-04 to PRE-07 |
| Experience | UX-07 dashboard, UX-08 export, UX-09 onboarding |
| Privacy and compliance | PRV-05, PRV-09, PRV-10, CMP-01 to CMP-04, CMP-06 |
| Platform and integrations | ING-09 payer FHIR API, PLT-05 performance, PLT-07 import layer, PLT-08 KPIs |

## Later (P3)

PRE-03 price transparency data, TAX-05 FSA expiry alerts, DSP-06 charity care screening, CMP-05 provider-facing data separation.
