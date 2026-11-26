Publishing the Google consent screen. You do this in the Google Cloud console; I can't do it for you. OWNER_SETUP.md has the same steps (lines 55–66 and 109).

Go to console.cloud.google.com and select the mhs-staging project.
Open Google Auth Platform (in older consoles: APIs & Services → OAuth consent screen).
Under Branding, check these are filled in:
App name: CareBack (the name the consent screen shows; changing it sends the brand back through Google's verification)
App home page: https://carebackhealth.com
Privacy policy: https://carebackhealth.com/privacy-notice
Terms of service: https://carebackhealth.com/terms. This page only exists once this branch is deployed to staging, so deploy before you publish.
Authorized domains: carebackhealth.com (keep myhealthspend.com beside it while its callbacks are registered)
Go to Audience and click Publish app, then confirm. The status changes from "Testing" to "In production", and any Google account can sign in, not just your listed test users.

What Google reviews:

The app only asks for openid, email and profile, which need no Google review. Publishing takes effect right away.
Uploading a logo or wanting the app name shown means Google must verify the brand first, in the Verification Center. Until then, people may see the domain in place of the name. You can publish without a logo and add one later.
In "Testing" mode a test user's sign-in expires after 7 days. That limit goes away once the app is published.

After publishing, on the app's admin screen turn on Consent before collection, then Open sign-up. Since you're limiting who gets in by other means, that's the only Google-side step left for Google sign-up.
