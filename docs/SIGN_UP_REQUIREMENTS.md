# Sign-up with Google or Microsoft (PRV-13)

Requested by the owner on 2026-11-21. Decision record: ADR-059 in [DECISIONS.md](DECISIONS.md). Backlog item B-24 (self-service sign-up) is the first part of this; B-25 (Apple) and B-26 (email) are what's left.

## 1. Summary

Today every member is created by `mhs-admin` and invited with an enrolment link (ADR-048: "invitation only"). Google and Microsoft sign-in work, but only for a member who has already linked the account.

PRV-13 lets a new person create their own account with a Google or Microsoft account, from a single "Log in or sign up" page like Dropbox's. Signing up creates a new household with the person as its first member, links the provider account, records that they agreed to the Terms of Service and Privacy Policy, and takes them to the authenticator step (while the code is required) and then Home, where onboarding (UX-09) picks up.

Only third-party sign-up is offered. Apple sign-up (B-25) and sign-up with an email address and password (B-26) are later.

## 2. Goals and non-goals

**Goals**

- G1. A person with a Google or Microsoft account can go from the landing page to their own empty household in under a minute, without anyone inviting them.
- G2. One page serves both returning members and new people: the person doesn't have to know which one they are.
- G3. The Terms of Service and Privacy Policy are linked on that page, and the new member explicitly agrees to them before an account exists. The version they agreed to and when are kept.
- G4. Nothing gets weaker: linking stays by provider and subject (never email), the authenticator code still applies while the owner requires it, household isolation is unchanged, and consent before collection (CMP-02) applies to every new member.
- G5. The owner decides when sign-up is open, from the admin screen, without a deploy.

**Non-goals (this release)**

- Sign-up with Apple (B-25). Apple is asked for no scope, so it returns no email (ADR-057), and asking for the email changes Apple's callback to a cross-site POST that the flow cookie doesn't survive. Existing members can still link and sign in with Apple.
- Sign-up or sign-in with an email address alone, with a magic link or code sent by email (B-26). It needs outbound mail and its own abuse controls.
- Inviting other people into a household you signed up for. Household members are still added with `mhs-admin add-member`; a self-service invite is a later requirement.
- Billing, plans or trials. "Sign up" is free; the page doesn't promise "free" because pricing isn't decided.
- Writing the Terms of Service. The app links to a Terms page that is a draft until the healthcare privacy attorney reviews it, like the privacy notice (ADR-055).

## 3. Users and stories

| ID | As | I want to | So that |
| --- | --- | --- | --- |
| US-1 | A new visitor | click "Continue with Google" (or Microsoft) and get an account | I can start reconciling my bills without waiting for an invitation |
| US-2 | A new visitor | read the Terms of Service and Privacy Policy before I agree | I know what happens to my health data |
| US-3 | A returning member with a linked account | use the same button and land in my household | I don't need to remember whether to "sign in" or "sign up" |
| US-4 | A returning member with a password | still sign in with my email and password | my existing account keeps working |
| US-5 | A new member who signed up | set up the authenticator and get recovery codes | I can get back in if I lose my phone or Google account |
| US-6 | The owner | open or close sign-up for the whole service | strangers can't put real health data in before the launch gate is passed |
| US-7 | A new member | export or delete my account without a password | I keep PRV-09's rights though I never set one |

## 4. The experience

### 4.1 The "Log in or sign up" page (`/signin`)

Shown to anyone without a session: from the landing page's "Sign in" link, an expired session, or sign-out.

When sign-up is **open**:

```
┌──────────────────────────────────────────┐
│          Log in or sign up               │
│                                          │
│  [ G   Continue with Google            ] │
│  [ ▦   Continue with Microsoft         ] │
│                                          │
│  ─────────────── or ───────────────      │
│  ▸ Sign in with email and password       │
│                                          │
│  By continuing, you agree to the Terms   │
│  of Service and acknowledge the Privacy  │
│  Policy.  (both are links)               │
│  Google or Microsoft will know you       │
│  signed in here, but sees nothing of     │
│  your records.                           │
└──────────────────────────────────────────┘
```

- **SU-01** The heading is "Log in or sign up". The provider buttons come first, full width, each with the provider's own logo and the words "Continue with Google" / "Continue with Microsoft", in the order Google, Microsoft (then Apple, if configured, for linked members only; see SU-08).
- **SU-02** Below an "or" divider, "Sign in with email and password" opens the existing email and password form (for members created by invitation). It's open already when the last attempt failed. There is no email sign-up field (B-26).
- **SU-03** The legal line under the buttons reads "By continuing, you agree to the Terms of Service and acknowledge the Privacy Policy." "Terms of Service" links to `/terms`, "Privacy Policy" to `/privacy-notice`. Both pages are public. The provider sentence from ADR-048 stays ("Google or Microsoft will know you signed in here, but sees nothing of your records"), with "You'll still enter your authenticator code" while the code is required.
- **SU-04** The buttons are plain links (GET), not forms, as ADR-048 requires under the page policy.

When sign-up is **closed**, the page is as today: heading "Sign in", the email and password form open, and the provider buttons under "Or, if you've linked an account". The Terms and Privacy links are shown either way.

The page meets the UI guide and the phone rules (ADR-041): 44px tap targets, nothing below 12px, works at 375px and 1280px, CSP-clean (logos are inline SVG in the template, no inline styles or scripts).

### 4.2 Coming back from the provider

The callback (`/signin/with/<provider>/callback`) already checks `state`, `nonce`, issuer, audience and expiry. After those checks:

| Case | Result |
| --- | --- |
| The provider account is linked to a member | Signed in as today: the code step, or Home's link when the code is off (SU-05) |
| Not linked; sign-up open; the provider allows sign-up; the email is verified; no member has that email | The "Create your account" page (4.3) |
| Not linked; sign-up open; a member already has that email | "There's already an account for <email>. Sign in with your email and password, then link <Provider> on your Account page." No account is created and nothing is linked (SU-09) |
| Not linked; sign-up open; the provider says the email isn't verified, or sent none | "<Provider> didn't confirm an email address for this account, so it can't be used to sign up." (SU-10) |
| Not linked; the provider is Apple | "Signing up with Apple isn't available yet. Use Google or Microsoft." (SU-08) |
| Not linked; sign-up closed | Today's answer, word for word, whatever the email (TC-PRV-12-2 still holds) |

- **SU-05** A linked account signs in exactly as PRV-12 does today. Sign-up changes nothing for linked accounts.

### 4.3 "Create your account"

```
┌──────────────────────────────────────────┐
│        Create your account               │
│  You're signing up with Google as        │
│  pat@example.com.                        │
│                                          │
│  Your name   [                     ]     │
│                                          │
│  [ ] I agree to the Terms of Service     │
│      and the Privacy Policy.             │
│                                          │
│  [        Create account         ]       │
│  Cancel                                  │
└──────────────────────────────────────────┘
```

- **SU-06** The page shows the provider and the verified email (read-only) and asks for one thing: the person's name, 1 to 80 characters, as it should appear in the household. The app doesn't ask the provider for the name (`profile` scope), keeping ADR-048's least data.
- **SU-07** A checkbox "I agree to the Terms of Service and the Privacy Policy", with both linked and opening in a new tab, must be ticked. It is unticked to start. Without it the page comes back with "Tick the box to agree to the Terms of Service and the Privacy Policy." This explicit agreement is what's recorded; the sentence on the sign-in page is notice only.
- **SU-11** The pending sign-up (provider, subject, verified email) is held on the server for 15 minutes against a random token in an `HttpOnly` cookie limited to `/signup`, with its own form token. It is used once. Nothing about it is in the URL. After 15 minutes, or with a missing or wrong cookie or form token, the page says "This sign-up has expired. Start again." and links to `/signin`.
- **SU-12** "Create account" (a same-site POST to `/signup`) creates, together:
  1. a household named "<name>'s household" with its own data key (PRV-06);
  2. a member in it with the name and the verified email, **no password**, a new authenticator secret, and the Terms and privacy notice versions they agreed to with the time;
  3. the link from the provider account (provider, subject, and the email for display) to that member.

  If any step fails, none of it remains. Two sign-ups racing for the same provider account or email produce one account; the other gets the SU-09 answer.
- **SU-13** The new member is not an owner and gets no admin rights.
- **SU-14** Signing up starts a session. While the code is required, the member goes straight to the code step, which shows the authenticator QR code to set up (as ADR-049 does for a member who never set one up). After the first correct code, a page shows ten recovery codes once, with "Continue" to Home. When the owner has turned the code off, the member lands on Home, and can make recovery codes on the Account page.
- **SU-15** Cancel, or closing the tab, creates nothing. The pending sign-up expires.

### 4.4 After sign-up

- **SU-16** Home shows onboarding (UX-09) for the empty household: add members, a plan, an account, a first document.
- **SU-17** Consent before collection (CMP-02) applies: the member is asked for consent before their first upload, forwarded email, import or insurer pull. Sign-up can only be opened while the owner requires consent (SU-22).
- **SU-18** A member without a password confirms who they are with the authenticator code wherever a member with a password types it: exporting their data, deleting their account, making new recovery codes. When the code is off for members, they confirm by having signed in within the last 10 minutes; otherwise the page asks them to sign out and sign in again, then retry.
- **SU-19** A member without a password can't unlink their last sign-in account (it would lock them out). The Account page says "You sign in with Google. It can't be unlinked while it's your only way in." They can link the other provider as a second way in.
- **SU-20** Recovery (ADR-037) works for them: a recovery code and their email give a new password and a new authenticator, so losing the Google or Microsoft account doesn't lose the household.
- **SU-21** The email and password form never signs in a member without a password, and says the same thing it says for a wrong password. Those tries don't count toward the lock, so nobody can lock a member out by guessing passwords they don't have.

### 4.5 The owner's controls

- **SU-22** The admin screen (PLT-09) gets a "Sign-up" card with one toggle, `allow_signup`, **off by default** so an upgrade never opens sign-up by itself. It can only be turned on while "Consent before collection" is required and at least one sign-up provider (Google or Microsoft) is configured and on; otherwise the screen says why. While sign-up is on, consent can't be turned off.
- **SU-23** Turning a provider off on the admin screen also stops sign-up through it. Turning sign-up off stops new sign-ups at once, pending ones included; members who already signed up are unaffected.
- **SU-24** The screen's counts add "Signed up themselves" (members created by sign-up). Counts only, no names (ADR-049).
- **SU-25** Every sign-up, refused sign-up and toggle change goes in the security log: `signup` (household and member), `signup_refused` (no ids), `setting_allow_signup_on/off` (the owner).

### 4.6 The landing page

- **SU-26** While sign-up is open, the landing page's "Sign in" link reads "Sign in or sign up", and the FAQ answer about uploading says accounts are open with a Google or Microsoft account instead of "by invitation" (ADR-047's note). While closed, both are as today.

## 5. Security and privacy requirements

- **SU-30 Linking by subject only.** The new member's link is the provider's subject, as in ADR-048. The email is the account's contact address and the sign-in name for recovery; it never links a provider account to an existing member.
- **SU-31 Verified email only.** Google: the ID token's `email_verified` is true. Microsoft: the account is a personal Microsoft account (tenant `9188040d-6c67-4c5b-b112-36a304b66dad`), or the token carries `xms_edov` true (the owner can add that optional claim in the Entra app registration to allow work and school accounts). An unverified email could let someone take an address that isn't theirs and block its owner from signing up.
- **SU-32 Same scopes.** Still only `openid email`; nothing more is asked of the provider for sign-up.
- **SU-33 Pending sign-ups are short-lived and single use**, stored as a hash of the token, and deleted on use or expiry. The cookie is `HttpOnly`, `SameSite=Strict`, `Secure` on TLS, path `/signup`.
- **SU-34 Cross-site posts** to `/signup` are refused by the existing origin check, and the form carries its own token.
- **SU-35 Abuse.** Each account needs a working Google or Microsoft sign-in, which is the main control. The owner can close sign-up at once. A cap on households per day is a later item if abuse appears (noted in ADR-059).
- **SU-36 No data before the code.** A new member reaches no household data until the code step is passed, while it's required.
- **SU-37 Staging.** Staging holds synthetic data only (ARCHITECTURE.md). Sign-up should stay off on staging except to test it, and must not be opened to the public before the launch gate (CMP-01 to CMP-04, PRV-09, attorney review) and the production project.

## 6. Data

| Change | Where |
| --- | --- |
| `app.members.password_hash` may be empty (a member who signed up with a provider has none) | migration `016_self_signup.sql` |
| `app.members.signed_up_with` (provider name, or empty for invited members), `terms_version`, `privacy_version`, `terms_accepted_at` | same |
| `app.pending_signups` (token hash, provider, subject, email, form token, expiry) | same |
| `allow_signup` in `app.service_settings`, default off | `features.py` |
| `TERMS_VERSION` beside the privacy notice's `NOTICE_VERSION` | `web/household/signup.py` |

## 7. Outside the code (owner)

1. **Google**: the OAuth consent screen must be **In production** (not "Testing", which only lets listed test users in), with the home page, Privacy Policy (`https://carebackhealth.com/privacy-notice`) and Terms of Service (`https://carebackhealth.com/terms`) links. `openid` and `email` need no Google verification review, but the brand (name and logo) does.
2. **Microsoft**: the app registration's supported account types must include personal Microsoft accounts (the app uses the `common` endpoint). Publisher verification removes the "unverified" warning on the consent screen. Add the `xms_edov` optional claim to allow work and school accounts.
3. **Terms of Service**: the draft at `/terms` needs the attorney's review, like the privacy notice.
4. **Admin screen**: require consent, then turn on sign-up, only when ready (SU-37).

## 8. Acceptance tests

Added to TEST_PLAN.md as TC-PRV-13-1 to TC-PRV-13-10 and automated in `tests/test_r1_signup.py` against the fake provider.

| TC | Scenario | Expected |
| --- | --- | --- |
| TC-PRV-13-1 | Sign-up open; a new Google account goes through sign-up, agrees, and enters the first code | Household, member (no password, versions and time recorded) and link created; QR shown; recovery codes shown once after the code; Home reachable; nothing reachable before the code |
| TC-PRV-13-2 | Sign-up closed (the default); a new account comes back | Today's refusal, word for word; nothing created |
| TC-PRV-13-3 | The provider account's verified email belongs to an existing member | "Already an account" answer; nothing created or linked |
| TC-PRV-13-4 | Unverified email (Google `email_verified` false; Microsoft work tenant without `xms_edov`); Apple | Refused with the reason; nothing created |
| TC-PRV-13-5 | Create account without ticking the box; with an empty name; with no or a wrong sign-up cookie or form token; after 15 minutes; twice with the same token | Refused; nothing created; the second use creates nothing more |
| TC-PRV-13-6 | Signed-up member: password form with their email; export, delete and new recovery codes with the code; unlink their only provider | Password form refuses without locking; the code confirms; unlink refused |
| TC-PRV-13-7 | Owner turns sign-up on without consent required; with it; turns consent off while sign-up is on | Refused, allowed, refused; each change logged |
| TC-PRV-13-8 | Two households sign up; each reads the other's ids | 404 everywhere (PRV-11 isolation holds for signed-up households) |
| TC-PRV-13-9 | The sign-in page with sign-up open and closed; the landing page | Heading, buttons, legal links to `/terms` and `/privacy-notice`, landing link and FAQ as in 4.1 and 4.6; `/terms` public |
| TC-PRV-13-10 | The sign-in and create-account pages at 375 and 1280 px in a real browser | No overflow, 44px targets, no policy violations |

## 9. Open questions for the owner

Tracked in BACKLOG.md as B-27 to B-30. The owner will open sign-up and limit who gets in by other means (2026-11-21).

1. **Household name.** "<name>'s household" by default. Should the member be able to rename it? (No rename page exists today.)
2. **Code for new members.** Recommended: keep the owner's setting (required by default), so a new member sets up an authenticator at sign-up. The alternative is to trust the provider's own second factor, which ADR-048 decided against.
3. **Work and school Microsoft accounts.** Off unless `xms_edov` is set up (SU-31). Is that acceptable for early access?
4. **Terms of Service text.** Who drafts it before the attorney review: the build session (as for the privacy notice) or the attorney?
