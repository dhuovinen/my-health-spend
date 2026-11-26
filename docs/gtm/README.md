# Go to market: CareBack

The track for how CareBack is described and launched: positioning, messages, and the launch and awareness assets built from them. Started 2026-11-25.

**Start with [BACKGROUND.md](BACKGROUND.md).** Every asset in this folder (deck, video, social, press, email) takes its claims, words and proof points from it. When an asset needs something the background doesn't say, add it to the background first, then use it.

## How this track relates to the others

| Topic | Where it lives | This track |
| --- | --- | --- |
| The name and why | [naming.md](../../naming.md), ADR-060 in [DECISIONS.md](../DECISIONS.md) | Uses it; doesn't reopen it |
| Mark, wordmark, colors, type, findings language | [UI_GUIDE.md](../UI_GUIDE.md), [REBRAND_PLAN.md](../REBRAND_PLAN.md) | Follows it; asset files come from `tools/make_brand_assets.py` |
| The landing page | `src/mhs/web/templates/landing.html` (ADR-047, REBRAND_PLAN §5) | Its copy is the current public wording; keep the two in step |
| What the product does, and when | [VISION.md](../VISION.md), [ROADMAP.md](../ROADMAP.md) | Claims only what is built and switched on |
| Competitors | [research/](../../research/) | Summarized in the background, §6 |

## Assets

| Asset | File | Status |
| --- | --- | --- |
| Background document | [BACKGROUND.md](BACKGROUND.md) | Draft, 2026-11-25; open questions in §10 |
| Talk track (narration for the deck and video) | [TALK_TRACK.md](TALK_TRACK.md) | Draft, 2026-11-25; wording choices to confirm at the end |
| About us: mission, ethos, founder's signature | [ABOUT.md](ABOUT.md) | On the landing page (`#about`, and the FAQ "Who is behind CareBack?"), 2026-11-25 |
| Short presentation (about 8 slides) | | Not started; outline in BACKGROUND §9 |
| Short video (60 to 90 seconds) | | Not started; outline in BACKGROUND §9 |
| One-page summary | | Not started |
| Social profiles and launch posts | | Waiting on handles (REBRAND_PLAN §8) |
| Press note | | Waiting on the launch gate |
| Member announcement ("now CareBack") | | Text in REBRAND_PLAN §7 |

## Rules for every asset

1. **No promise of money back or savings.** "We've got your back", "help you ask for it back" and "find what may be owed to you" are fine; "get your money back", "recover $X" and savings totals are not (UI_GUIDE "Findings language").
2. **Only what is true today.** Each capability claim names something built and switched on for the people the asset reaches. Mark anything else "coming".
3. **Fictional samples are labelled.** Use the landing page's Riverview example or `samples/demo/`; never real bills or the owner's data.
4. **Every statistic has a dated source** in the background document, or it isn't used.
5. **No mention of the old name** in public assets (owner, 2026-11-25), except a member announcement that explains the change.
