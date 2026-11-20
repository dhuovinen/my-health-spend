# UI guide

The brand standard for the app, the website, decks and marketing. It was built from myhealthspend.com and `src/mhs/web/static/style.css` on 2026-11-05.

- Full style guide with live components: https://claude.ai/artifact/93oE8yMM7LQcxzXn5FwZcU
- Scorecard and competitor benchmark: https://claude.ai/artifact/FK7DcQbdRJGYUy1GH4Xgq3

The app is on this standard, with Manrope and DM Sans self-hosted in `src/mhs/web/static/fonts/`.

## Brand rules

- **Idea:** three separate stories, one clear picture. Show the three sides of a visit, where they disagree, and the dollar gap.
- **Traits:** clear, on your side, careful.
- **Name:** "My Health $pend" in anything people see. "My Health Spend" in alt text, `aria-label`, file names and code.
- **Findings language:** "potential discrepancy" and "worth a closer look" until confirmed. Always name the amount. Promise no savings.
- **Statistics:** every figure needs a source. `$500B+` and `$25-50B` are unverified, so keep them off new material.
- **Samples:** only fictional documents, labeled as fictional where they appear.

## Tokens

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `background` | #FFFFFF | #131D2D | Ground |
| `foreground` | #151F30 | #F6F9FC | Text |
| `primary` | #1A5CDF | #7EA8FF | The one action color |
| `primary-foreground` | #FFFFFF | #0B1A36 | Text on primary |
| `muted` | #F3F5F9 | #1B2739 | Neutral fill, app ground |
| `muted-foreground` | #58616F | #ADB5C1 | Supporting text |
| `secondary` | #F2F5FB | #1B2739 | Quiet band |
| `accent` | #E5EFFF | #1D2E4D | Tint, selected tab |
| `hero-surface` | #EEF2F7 | #182334 | Hero ground |
| `dark-surface` | #131D2D | #0E1623 | Closing band |
| `border` | #D9DEE7 | #2F3B4F | Hairlines only |
| `input-border` | #6E7787 | #7A889C | Field and quiet button edges |
| `red-pen` | #B42318 | #FF8A80 | Findings only |
| `red-pen-soft` | #FDECEA | #3A1D1B | Fill behind red-pen text |
| `coral` | #DD574B | #FF8A80 | Illustration only, 24px and up |

Status colors keep the current app values in `style.css` (`--warn`, `--info`, `--good`, `--idle`, and their soft fills). A status always carries its word.

**Type:** Manrope for headings (58/65, 36/45, 18/27), DM Sans for text. Body is 16/26, and nothing goes below 12px. Self-host both in the app, because its policy is `font-src 'self'`. DM Sans has no tabular digits, so money columns use Manrope with `tabular-nums` (`.num` in the app).

**Shape:** 5px buttons, 6px tiles, 7px cards. Hairlines over cards, a shadow only on things that float, no gradients. Icons are Lucide outline at 2px.

## How the app moved

| App | Was | Now |
| --- | --- | --- |
| `--accent` | #0f766e | #1a5cdf |
| `--accent-soft` | #e3f3f1 | #e5efff |
| `--bg` | #f6f7f9 | #f3f5f9 |
| `--surface-2` | #f0f2f5 | #f2f5fb |
| `--text` | #18212b | #151f30 |
| `--muted` | #5b6673 | #58616f |
| `--border` | #dde2e8 | #d9dee7 |
| `--radius` | 10px | 7px |
| Button and input radius | 8px | 5px |
| Body | System stack, 15px | DM Sans, 16px |
| `.hero` | Teal gradient | Flat `dark-surface` (`hero-surface` is too close to the app ground) |
| `.brand` | Plain name | Wordmark with `$` in `primary` |
| `favicon.svg` | Teal heart | The blue mark |

Dark theme values are in the table above. In the app, dark `--bg` is `background`, `--surface` is `hero-surface` and `--surface-2` is `accent`, so cards sit lighter than the page. The favicon is the old heart recolored: the website's mark is a PNG, and a vector master is still needed.
