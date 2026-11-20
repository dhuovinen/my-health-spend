# Breach response plan

**Status: draft (ADR-055).** For review by a healthcare privacy attorney before anyone outside the owner's household is invited (the launch gate in ROADMAP.md). It covers CMP-01 (the FTC Health Breach Notification Rule, 16 CFR Part 318). The tabletop exercise (TC-CMP-01-2) and automated anomaly alerts (TC-CMP-01-3) are still to do.

## What counts

A breach is any acquisition of a member's identifiable health information without the member's authorization: an outside attack, but also data sent somewhere it shouldn't go by mistake (an email to the wrong person, a misconfigured bucket, identifiers reaching the AI service). Under the rule, an unauthorized disclosure is a breach even with no attacker.

## Who does what

| Role | Who | Does |
| --- | --- | --- |
| Incident lead | The service owner (`app.members.is_owner`) | Decides it's an incident, runs this plan, signs the notices |
| Technical responder | Whoever operates the deployment | Contains, collects evidence, restores |
| Counsel | The healthcare privacy attorney | Confirms whether notice is required and reviews every notice before it goes out |

## Where incidents are noticed

- `app.security_log`: sign-in failures, locks, social sign-ins, setting changes, consent changes, insurer pulls (`payer_pull`, `payer_pull_failed`).
- The access log per household (ADR-040): who viewed or changed which records.
- Outbound capture in tests (TC-PRV-01-1, TC-PLT-04-1) and, in staging and production, Google Cloud audit logs for Cloud Storage, Cloud SQL and Cloud KMS.
- Reports from members, providers, insurers or the hosting provider.

## Steps

1. **Record it** the day it's noticed: time found, who found it, what's known. The 60-day clock starts at discovery, or when it would have been discovered with reasonable diligence.
2. **Contain:** end sessions (`DELETE FROM app.sessions`), turn the authenticator code back on (admin screen), rotate the exposed secrets in the secrets volume or Secret Manager, revoke the affected keys in Cloud KMS if key material is involved, and block the route data left by.
3. **Preserve evidence:** copy the security log, the affected households' access logs and the cloud audit logs before anything rotates them out.
4. **Scope it:** which households and members, which records (documents, claims, identifiers from the vault), and over what time.
5. **Decide on notice with counsel.** If identifiable health information was acquired without authorization, notice is required.
6. **Notify:**
   - **Each affected member,** by email (members' addresses are in `app.members`), without unreasonable delay and **no later than 60 calendar days after discovery**. The notice says what happened, what information was involved, what members should do, what MHS is doing, and how to reach us. Plain language.
   - **The FTC:** for 500 or more people, at the same time as the members (and no later than 60 days after discovery); for fewer than 500, in a yearly log submitted within 60 days after the end of the calendar year.
   - **The media:** if 500 or more residents of one state or jurisdiction are affected, prominent media there, in the same window.
   - **Third parties** the rule names (vendors, the hosting provider) as their contracts require.
7. **Fix and review:** fix the cause, add a test for it, and write a short report into DECISIONS.md if it changes a decision.

## Keeping it ready

- Review this plan yearly (CMP-06) and after any change to where data goes.
- Run a tabletop exercise before launch and yearly after (TC-CMP-01-2).
- Keep the security log's one-year retention (ADR-038) at least as long as the FTC's reporting window needs.
