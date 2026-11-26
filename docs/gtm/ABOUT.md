# About us: copy for the website

*Revised 2026-11-25 with the owner's answers. The source for the "About us" section of the landing page (`#about` in `src/mhs/web/templates/landing.html`), signed by Don with his photo (`static/landing/don-huovinen.jpg`) and his LinkedIn profile. The page uses a shortened version of this text; keep the two in step.*

---

## Mission

> CareBack helps people check every medical bill, fix what's wrong and pay only what they owe, in the most efficient way, at no cost.

Headline form, used on the page: **Check every bill. Fix what's wrong. Pay only what you owe.**

Shortest form, for a footer or a slide: **Fair medical bills for everyone, at no cost.**

## About CareBack

Healthcare is eighteen percent of the American economy, and more of its cost lands on each of us every year. When a bill is wrong, we're the first line of defense, without the billing experts the insurers have.

I learned that the hard way. Over a series of monthly treatments, the same care was coded and billed differently, and I was paying more. I found it, asked my provider to fix it, and they did. Then I heard the same story from friends and colleagues. I didn't need to fix this for myself. It needs fixing, period. That's why I started CareBack.

### How we work

**A community service, at no cost.** Lots of companies will help with your medical bills for a fee or a percentage of what they save you. That isn't us. CareBack is free to use. If it proves its value, our aim is to partner with a leading nonprofit to keep providing it at no cost.

**Advocates that work for you.** CareBack checks every bill, explanation of benefits and payment, finds where they disagree and drafts what to say. Today you review it and send it. Next, with your permission, CareBack will hand its findings and analysis to your own AI agent, or act for you directly, through open standards for personal agents such as A2A, MCP and Poppy.

**Paying the efficient way.** We believe your HSA is the most efficient way to pay for care. CareBack shows which expenses it can likely cover and keeps the receipts, so you can pay for your care in the most efficient way possible.

**100% open source.** Our code is public and free for anyone to use. Our goal isn't to find a problem many people share and make money from it. It's to solve it, for everyone, at no cost. If you run a nonprofit that can do this better or reach more people, I'd be glad to work with you, support you or follow your lead. It isn't about me. It's about the outcome.

When it comes to your medical bills, we've got your back.

**Don Huovinen**, founder · [LinkedIn](https://www.linkedin.com/in/don-huovinen-288399/)

---

## Notes

1. **Nonprofit.** CareBack is described as a community service at no cost, aiming to partner with a leading nonprofit if it proves its value (owner, 2026-11-25). It doesn't call itself a nonprofit.
2. **Advocating on your behalf** is directional (owner, 2026-11-25). Today letters are drafted on request, never stored and never sent by CareBack (ADR-042). Handing findings to a member's own agent, or acting for them through A2A, MCP or Poppy (Sierra's draft Personal Agent Protocol), needs an ADR before it's built: it changes "the member sends" and decides what leaves the app tier. The owner leans toward A2A or MCP over Poppy and runs Poppy privately today.
3. **HSA, not taxes.** The position is that paying from the HSA is the most efficient approach; the page says nothing about taxes. The footer's "Not insurance, medical, legal or financial advice" still applies, and the app's HSA and tax page keeps its own disclaimer (CMP-04).
4. **Free, not "free forever".** "Free to use" and "at no cost" leave room for the nonprofit partnership without promising terms another organization would set.
5. **No link to the code yet.** The repository is public (MIT) but still named after the old brand, which the page never mentions. Link it once the repository is renamed.
6. **The LinkedIn link is the page's only link off the site.** PRV-08's test (`tests/test_r1_csp.py`) allows it by name in `OUTBOUND_LINKS`: it's a plain link, not something the page loads, and with `Referrer-Policy: same-origin` and `rel="noopener noreferrer"` it sends LinkedIn nothing. Add any other outbound link there.
7. **The photo** came from the owner on 2026-11-25 and is served from the app (the page loads nothing from LinkedIn, and the security policy only allows the site's own images).
