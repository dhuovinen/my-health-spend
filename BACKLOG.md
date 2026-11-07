# BACKLOG

Items deferred from the MVP. Newest decisions are in `docs/MVP_REQUIREMENTS.md` section 9.

| ID | Item | Origin | Notes |
| --- | --- | --- | --- |
| B-1 | Automatic extraction from PDFs/images into the ingest JSON, with a confirm step | Plan phase 2 | Raises ND-9 if an outside OCR/AI service is used. |
| B-2 | Agreed rate from provider billing | Owner, 2026-10-09 | Review whether bills reliably show a rate (`rate` field already in the bill line) and how it compares to the EOB `allowed`. |
| B-3 | Supplements and equipment: HSA/FSA eligibility, and member-submitted claims to insurance that may count toward the deductible | Owner, 2026-10-09 | Unknown whether insurers accept these or whether it varies by plan. Needs research before modelling. |
| B-4 | Ledger over time: chart of charges, payments and running balance per provider and overall | Owner, 2026-10-09 | MVP has the ledger table only. |
| B-5 | Confirmed HSA/FSA eligibility rules (replace "possible opportunity" with eligible / not eligible / needs a letter of medical necessity) | Owner, 2026-10-09 | Built 2026-10-18 as "likely" tags (TAX-01, ADR-021, ADR-043); still possibilities, not rulings. |
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
| B-17 | Account fee flags (e.g. HSA paper-statement fees) as savings opportunities | Real data, 2026-10-09 | Built 2026-10-18 (merged 2026-10-18): the HSA and tax page lists the year's HSA fees as a possible saving. |
| B-18 | Importers for other insurers and HSA providers | Real data, 2026-10-09 | `tools/build_ingest.py` handles one claims CSV layout and one HSA export layout. |
| B-19 | HSA contribution tracking against the annual IRS limit | Real data, 2026-10-09 | Built 2026-10-18 (TAX-06, ADR-043). |
| B-20 | Statement parsers for other provider billing systems | Real data, 2026-10-09 | One layout supported (Southeastern Retina). |
| B-21 | Prior-year (2025) HSA history | Real data, 2026-10-09 | Needed to close 2025 Southeastern Retina payments; HSA export starts 2026-01-14. |
| B-22 | Follow-up tracking on provider notes (open / resolved, follow-up date, reminders) | Owner, 2026-10-09 | MVP notes are a plain dated log. |
| B-23 | Sign-in: tell a wrong password apart from a locked account | Owner, 2026-11-06 | Not built. One message covers two conditions, and the code step hides a lock completely. Needs an ADR. See [B-23 in detail](#b-23-in-detail). |

## B-23 in detail

**The problem.** A wrong password and a locked account are different conditions needing different actions: one means try again or recover the account, the other means stop and wait. The app gives both one answer, so a member can't tell which applies. They may keep retrying during a lock, or wait 15 minutes for nothing.

**How it was found.** On 2026-11-06 the owner tried a harness login (`csv-trumans-20261107-024720@example.test`) and saw "That email and password don't match, or the account is locked for 15 minutes after too many tries." The account wasn't locked: it had one failed attempt, and the password in the report signs in. The message left open which it was, so it couldn't help.

**Where it happens** (`src/mhs/web/household/`)

| Step | What the member sees | Conditions it covers |
| --- | --- | --- |
| Sign-in, `/signin` (`app.py`) | "That email and password don't match, or the account is locked for 15 minutes after too many tries." | Unknown email, wrong password, locked account |
| Authenticator code, `/signin/mfa` (`app.py`) | "That code didn't work. Use the current code from your authenticator app." | Wrong or reused code, **and** locked account. This one never mentions the lock, so a locked member with the right code is told to try another code |
| Recovery, `/recover` (`app.py`) | "That email and recovery code don't match, the code was already used, or the account is locked for 15 minutes after too many tries." | Unknown email, wrong code, used code, locked account |

**How the lock works today** (`auth.py`). Five failures lock the account for 15 minutes, counted together across password, authenticator code and recovery code. While locked, even the right password is refused. The count resets only after a right authenticator code or a change of password or MFA. An unknown email has no account, so it never locks, yet it gets the same wording.

**Why the message is combined, and the catch.** It looks deliberate: `check_password` says these cases are "indistinguishable". Only a real account can lock, so a plain "this account is locked" would tell anyone who tries five wrong passwords that the email has an account, and for a health app that itself reveals something. ADR-031 records the five tries and 15 minutes but not this choice. Any fix has to keep that protection or decide, in an ADR, to give it up.

**Recommended fix.** Separate messages without revealing which emails have accounts:

- **Wrong details:** "That email and password don't match." Unknown email and wrong password stay one message.
- **Locked:** "Too many tries. Sign-in for this email is paused for N minutes. You can try again at 3:42 PM, or use account recovery afterwards." It is based on the time really left.
- **Unknown emails lock too:** count failures per submitted email (stored hashed), so five wrong tries show the same lock message whether or not the account exists. This is the part that keeps the protection, and it needs a new table and a migration.
- **Authenticator step:** when locked, show the lock message and not "that code didn't work".
- **Recovery step:** the same separation. Whether to separate a used code from a wrong one is part of the decision, since it would confirm a code was once real.

**Decisions for the ADR**

1. Keep hiding which emails have accounts (recommended), or accept revealing it for simplicity.
2. Warn before the lock ("1 try left")? This helps members, but tells an attacker when to stop.
3. Whether a lock can be used against someone: anyone who knows a member's email can lock them out by trying wrong passwords. That is true today, and a clearer message makes it visible.

**Done when**

- Each condition has its own tested message on all three steps, added as new PRV-11 cases in `docs/TEST_PLAN.md`.
- A wrong password on a real email and on an unknown email give the same message, status and timing; so do their locks after five tries.
- A locked member with the right password or right code sees the lock message, with the correct time left; once it lifts, they can sign in.
- `tests/test_r1_auth.py::test_lockout_after_repeated_failures`, which today checks only the 401 status, also checks the wording.
- The Help page explains what to do when locked.
