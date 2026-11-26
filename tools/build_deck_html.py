"""Build a standalone HTML copy of the CareBack deck, for review in a browser and by /impeccable critique or audit.

The deck itself lives in a Claude Slides artifact (docs/gtm/README.md). Its source files are copied into
docs/gtm/deck/source/ (deck.json, deck.css, slides/<id>.html, exactly as the artifact stores them); this script
joins them into docs/gtm/deck/careback-deck.html:

- each slide at its real 1920x1080 size, scaled to the page width, in deck order, with its speaker notes under it;
- the fonts, the mark and Don's photo from src/mhs/web/static (nothing loaded from the web);
- the artifact's <x-icon> elements drawn as inline Lucide icons, and its uploaded images (/_blob/<id>) as files.

    uv run tools/build_deck_html.py

Rerun after copying newer slide files from the artifact. Edit the slides in the artifact, not the output.
"""
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECK = ROOT / "docs" / "gtm" / "deck"
SOURCE = DECK / "source"
OUT = DECK / "careback-deck.html"
STATIC = "../../../src/mhs/web/static"  # from docs/gtm/deck/

# Uploaded artifact assets, by id, and the repo files they were uploaded from.
BLOBS = {
    "/_blob/2a10f74ba7f7c94c06d82f8302cda415": f"{STATIC}/brand/mark.svg",
    "/_blob/2469cc3fa69e0c7dbc2f4a8d8ebfeaab": f"{STATIC}/landing/don-huovinen.jpg",
}

# The Slides type's icon names used by the deck, drawn as Lucide outline icons (ISC licence) at a 2px stroke.
ICONS = {
    "CheckCircle": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "Search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "Chat": '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>',
    "Clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "Users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
             '<path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "Code": '<path d="m16 18 6-6-6-6"/><path d="m8 6-6 6 6 6"/>',
    "Trust": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 '
             '6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
}

PAGE_CSS = f"""
@font-face {{ font-family: "DM Sans"; src: url("{STATIC}/fonts/dm-sans.woff2") format("woff2"); font-weight: 100 1000; font-display: swap; }}
@font-face {{ font-family: "Manrope"; src: url("{STATIC}/fonts/manrope.woff2") format("woff2"); font-weight: 200 800; font-display: swap; }}
html {{ background: #e4e8ef; }}
body.deck-page {{ margin: 0; padding: 32px 16px 64px; font: 16px/26px "DM Sans", Arial, sans-serif; color: #151f30; }}
.deck-head {{ max-width: 1200px; margin: 0 auto 24px; }}
.deck-head h1 {{ font: 750 28px/36px Manrope, Arial, sans-serif; margin: 0 0 6px; letter-spacing: 0; }}
.deck-head p {{ margin: 0; color: #58616f; font-size: 15px; line-height: 24px; }}
.slide {{ max-width: 1200px; margin: 0 auto 40px; }}
.slide-label {{ font: 600 13px/18px "DM Sans", Arial, sans-serif; color: #58616f; margin: 0 0 8px; }}
.frame {{ position: relative; width: 100%; aspect-ratio: 16 / 9; overflow: hidden; border-radius: 7px; box-shadow: 0 1px 2px rgba(16, 24, 40, .06); container-type: inline-size; }}
.frame > section {{ position: absolute; top: 0; left: 0; width: 1920px; height: 1080px; transform-origin: 0 0; transform: scale(var(--scale, .625)); }}
.notes {{ margin: 12px 0 0; padding: 14px 16px; background: #ffffff; border: 1px solid #d9dee7; border-radius: 7px; }}
.notes h2 {{ font: 600 13px/18px "DM Sans", Arial, sans-serif; color: #58616f; margin: 0 0 6px; text-transform: none; letter-spacing: 0; }}
.notes p {{ font-size: 15px; line-height: 24px; color: #151f30; margin: 0 0 8px; }}
.notes p:last-child {{ margin-bottom: 0; }}
x-icon {{ display: block; }}
x-icon svg {{ width: 100%; height: 100%; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }}
@media (prefers-reduced-motion: reduce) {{ .in {{ animation: none !important; }} }}
"""


def icon(match: re.Match) -> str:
    name = match.group(1)
    paths = ICONS[name]  # an icon the deck uses must be listed above
    return f'<x-icon name="{name}"><svg viewBox="0 0 24 24" aria-hidden="true">{paths}</svg></x-icon>'


def slide(sid: str, number: int, total: int) -> str:
    text = (SOURCE / "slides" / f"{sid}.html").read_text().strip()
    for blob, path in BLOBS.items():
        text = text.replace(blob, path)
    # Images uploaded in the deck itself: use a local copy in source/assets/<id>.<ext> (git-ignored, since their
    # licence is unknown), else leave a labelled gap so the review copy still builds.
    for blob_id in set(re.findall(r"/_blob/([0-9a-f]{32})", text)):
        local = sorted((SOURCE / "assets").glob(f"{blob_id}.*"))
        if local:
            text = text.replace(f"/_blob/{blob_id}", f"source/assets/{local[0].name}")
        else:
            text = text.replace(f'src="/_blob/{blob_id}"', 'src="" data-missing="uploaded in the deck; copy it to source/assets/"')
    text = re.sub(r'<x-icon name="(\w+)"></x-icon>', icon, text)
    notes = ""
    found = re.search(r"<aside>(.*?)</aside>", text, re.S)
    if found:
        text = text.replace(found.group(0), "")
        paras = "".join(f"<p>{html.escape(p.strip(), quote=False)}</p>"
                        for p in html.unescape(found.group(1)).split("\n\n") if p.strip())
        notes = f'<div class="notes"><h2>Speaker notes</h2>{paras}</div>'
    return (f'<article class="slide" id="slide-{number}" aria-label="Slide {number} of {total}">'
            f'<p class="slide-label">Slide {number} of {total} · {sid}</p>'
            f'<div class="frame">{text}</div>{notes}</article>')


def main() -> None:
    index = json.loads((SOURCE / "deck.json").read_text())
    order = index["order"]
    deck_css = (SOURCE / "deck.css").read_text()
    # The deck's `section`, `body` and heading rules are written for one slide per page; scope them to the frames.
    deck_css = re.sub(r"^body \{", ".frame {", deck_css, flags=re.M)
    title = html.escape(index["title"])
    slides = "\n".join(slide(sid, n, len(order)) for n, sid in enumerate(order, 1))
    OUT.write_text(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<!-- Built by tools/build_deck_html.py from docs/gtm/deck/source/; edit the slides in the artifact, not here. -->
<style>
{deck_css}
{PAGE_CSS}
</style>
</head>
<body class="deck-page">
<main>
<header class="deck-head"><h1>{title}</h1><p>{len(order)} slides at 1920×1080, with the speaker notes under each. A review copy of the Claude Slides deck (docs/gtm/README.md).</p></header>
{slides}
</main>
<script>
// Scale each 1920x1080 slide to its frame's width (CSS can't divide lengths in every browser yet).
const fit = () => document.querySelectorAll(".frame").forEach(f => f.style.setProperty("--scale", f.clientWidth / 1920));
fit(); addEventListener("resize", fit);
</script>
</body>
</html>
""")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(order)} slides")


if __name__ == "__main__":
    main()
