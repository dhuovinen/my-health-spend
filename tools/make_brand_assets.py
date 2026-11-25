# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["fonttools>=4.55", "brotli>=1.1", "uharfbuzz>=0.42", "pillow>=11", "playwright==1.64.0"]
# ///
"""Write the CareBack brand files (ADR-060, docs/REBRAND_PLAN.md §2) from one definition of the mark.

The mark is concept B, "the C-loop": the letter C drawn as an arrow that turns back on itself, closing on a check,
white on a #1A5CDF tile. The wordmark is Manrope at weight 750, outlined into SVG paths so it looks the same where
the font isn't loaded; "Care" takes the text color and "Back" the primary color.

Writes (the files are committed; rerun after changing the mark, the colors or the social image's text):

    src/mhs/web/static/favicon.svg            browser tabs (the small-size drawing, heavier strokes)
    src/mhs/web/static/favicon.ico            16, 32 and 48 px, for /favicon.ico
    src/mhs/web/static/apple-touch-icon.png   180 px, square and opaque (iOS rounds the corners)
    src/mhs/web/static/icon-192.png, icon-512.png, icon-maskable-512.png, site.webmanifest
    src/mhs/web/static/og-image.png           1200x630 link preview
    src/mhs/web/static/brand/                 mark.svg (master), wordmark{,-dark,-mono}.svg, lockup{,-dark}.svg
    src/mhs/web/static/landing/mark.svg       the landing page's navbar and footer mark
    docs/brand/oauth-logo-120.png             Google's consent screen (not served by the app)

Usage (PNGs are drawn by Playwright's Chromium: `uv run playwright install chromium` once):

    uv run tools/make_brand_assets.py
"""

import io
import json
import tempfile
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "src/mhs/web/static"
FONT = STATIC / "fonts/manrope.woff2"

PRIMARY, PRIMARY_DARK = "#1a5cdf", "#7ea8ff"
FOREGROUND, FOREGROUND_DARK = "#151f30", "#f6f9fc"
DARK_SURFACE, MUTED_DARK = "#131d2d", "#adb5c1"
WEIGHT = 750
NAME = ("Care", "Back")


# ---------- the mark (a 64-unit grid) ----------

def glyph(heavy: bool = False) -> str:
    """The white C-loop and check. `heavy` thickens the strokes so the mark holds up at 16 and 32 px."""
    ring, check = (7, 5.5) if heavy else (6, 4.5)
    return (f'<path d="M42.6 42.6A15 15 0 1 1 40.4 20.2" fill="none" stroke="#fff" stroke-width="{ring}" '
            'stroke-linecap="round"/>'
            '<path d="M47.6 25.3 43.4 15.0 36.4 24.9z" fill="#fff" stroke="#fff" stroke-width="2" '
            'stroke-linejoin="round"/>'
            f'<path d="M25.5 32.5l4.5 4.5 8.5-9" fill="none" stroke="#fff" stroke-width="{check}" '
            'stroke-linecap="round" stroke-linejoin="round"/>')


def mark_svg(heavy: bool = False, square: bool = False, title: str = "CareBack") -> str:
    """The tile with the glyph. `square` drops the rounded corners, for icons the platform crops itself."""
    radius = "" if square else ' rx="14"'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="{title}">'
            f'<rect width="64" height="64"{radius} fill="{PRIMARY}"/>{glyph(heavy)}</svg>\n')


# ---------- the wordmark ----------

def outlined_name(font_size: float) -> tuple[list[str], float, float, float]:
    """Each part of the name as an SVG path at `font_size`, shaped with kerning; the baseline is y=0.
    Returns the two paths, the total advance, the cap height and the descender (both positive)."""
    font = TTFont(FONT)
    font.flavor = None  # HarfBuzz reads TrueType, not WOFF2
    buffer = io.BytesIO()
    font.save(buffer)
    upem = font["head"].unitsPerEm
    scale = font_size / upem
    hb_font = hb.Font(hb.Face(buffer.getvalue()))
    hb_font.set_variations({"wght": WEIGHT})
    text = "".join(NAME)
    hb_buf = hb.Buffer()
    hb_buf.add_str(text)
    hb_buf.guess_segment_properties()
    hb.shape(hb_font, hb_buf, {"kern": True, "liga": True})
    glyph_set = font.getGlyphSet(location={"wght": WEIGHT})
    order = font.getGlyphOrder()
    paths, x, cluster_split = ["", ""], 0.0, len(NAME[0])
    for info, pos in zip(hb_buf.glyph_infos, hb_buf.glyph_positions):
        pen = SVGPathPen(glyph_set)
        glyph_set[order[info.codepoint]].draw(
            TransformPen(pen, (scale, 0, 0, -scale, (x + pos.x_offset) * scale, -pos.y_offset * scale)))
        paths[0 if info.cluster < cluster_split else 1] += pen.getCommands()
        x += pos.x_advance
    cap = font["OS/2"].sCapHeight * scale
    descender = -font["hhea"].descent * scale
    return paths, x * scale, cap, descender


def wordmark_svg(care: str, back: str, size: float = 60) -> str:
    paths, width, cap, _ = outlined_name(size)
    pad = size * 0.04
    w, h = width + 2 * pad, cap + 2 * pad
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.1f} {h:.1f}" role="img" aria-label="CareBack">'
            f'<g transform="translate({pad:.1f} {cap + pad:.1f})">'
            f'<path fill="{care}" d="{paths[0]}"/><path fill="{back}" d="{paths[1]}"/></g></svg>\n')


def lockup_svg(care: str, back: str, size: float = 60) -> str:
    """The mark beside the wordmark, centred on the cap height: mark 1.47x the font size, gap 0.4x."""
    paths, width, cap, _ = outlined_name(size)
    mark = size * 1.47
    gap = size * 0.4
    w = mark + gap + width
    baseline = mark / 2 + cap / 2
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.1f} {mark:.1f}" role="img" aria-label="CareBack">'
            f'<svg width="{mark:.1f}" height="{mark:.1f}" viewBox="0 0 64 64">'
            f'<rect width="64" height="64" rx="14" fill="{PRIMARY}"/>{glyph()}</svg>'
            f'<g transform="translate({mark + gap:.1f} {baseline:.1f})">'
            f'<path fill="{care}" d="{paths[0]}"/><path fill="{back}" d="{paths[1]}"/></g></svg>\n')


# ---------- rendering ----------

def render(page, svg: str, size: int, transparent: bool = True) -> Image.Image:
    page.set_viewport_size({"width": size, "height": size})
    page.set_content(f'<html><body style="margin:0;background:transparent">'
                     f'<div style="width:{size}px;height:{size}px">{svg.replace("<svg ", f"<svg width={size} height={size} ", 1)}</div>'
                     '</body></html>')
    png = page.screenshot(omit_background=transparent, clip={"x": 0, "y": 0, "width": size, "height": size})
    return Image.open(io.BytesIO(png)).convert("RGBA")


def og_image(page, out: Path) -> None:
    """The link preview: the dark lockup and what the service does, on the closing band's dark surface. It says
    what CareBack does rather than a tagline, so it stays true until the owner picks one (REBRAND_PLAN.md §1)."""
    lockup = lockup_svg(FOREGROUND_DARK, PRIMARY_DARK, 56)
    html = f"""<!doctype html><html><head><style>
      @font-face {{ font-family: Manrope; src: url("{FONT.as_uri()}") format("woff2"); font-weight: 200 800; }}
      @font-face {{ font-family: "DM Sans"; src: url("{(STATIC / 'fonts/dm-sans.woff2').as_uri()}") format("woff2"); font-weight: 100 1000; }}
      body {{ margin: 0; width: 1200px; height: 630px; background: {DARK_SURFACE}; color: {FOREGROUND_DARK};
              display: flex; flex-direction: column; justify-content: space-between; padding: 80px 88px; box-sizing: border-box; }}
      .lockup svg {{ height: 82px; width: auto; }}
      h1 {{ font: 750 64px/74px Manrope, sans-serif; margin: 0; letter-spacing: -0.5px; max-width: 980px; }}
      h1 span {{ color: {PRIMARY_DARK}; }}
      p {{ font: 500 26px/36px "DM Sans", sans-serif; color: {MUTED_DARK}; margin: 0; }}
    </style></head><body>
      <div class="lockup">{lockup}</div>
      <h1>Your bill, your insurer’s EOB and what you paid. <span>Side by side.</span></h1>
      <p>carebackhealth.com</p>
    </body></html>"""
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(html)
    page.set_viewport_size({"width": 1200, "height": 630})
    page.goto(Path(f.name).as_uri())
    page.evaluate("document.fonts.ready")
    out.write_bytes(page.screenshot(clip={"x": 0, "y": 0, "width": 1200, "height": 630}))
    Path(f.name).unlink()


def write(path: Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())
    print(path.relative_to(ROOT))


def main() -> None:
    brand = STATIC / "brand"
    write(brand / "mark.svg", mark_svg())
    write(STATIC / "favicon.svg", mark_svg(heavy=True))
    write(STATIC / "landing/mark.svg", mark_svg())
    write(brand / "wordmark.svg", wordmark_svg(FOREGROUND, PRIMARY))
    write(brand / "wordmark-dark.svg", wordmark_svg(FOREGROUND_DARK, PRIMARY_DARK))
    write(brand / "wordmark-mono.svg", wordmark_svg(FOREGROUND, FOREGROUND))
    write(brand / "lockup.svg", lockup_svg(FOREGROUND, PRIMARY))
    write(brand / "lockup-dark.svg", lockup_svg(FOREGROUND_DARK, PRIMARY_DARK))
    write(STATIC / "site.webmanifest", json.dumps({
        "name": "CareBack", "short_name": "CareBack", "start_url": "/", "display": "standalone",
        "background_color": "#ffffff", "theme_color": PRIMARY,
        "icons": [{"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
                  {"src": "/static/icon-maskable-512.png", "sizes": "512x512", "type": "image/png",
                   "purpose": "maskable"}]}, indent=2) + "\n")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=1)

        def png(svg: str, size: int, path: Path, opaque: bool = False) -> None:
            buf = io.BytesIO()
            image = render(page, svg, size, transparent=not opaque)
            (image.convert("RGB") if opaque else image).save(buf, "PNG", optimize=True)
            write(path, buf.getvalue())

        png(mark_svg(square=True), 180, STATIC / "apple-touch-icon.png", opaque=True)
        png(mark_svg(), 192, STATIC / "icon-192.png")
        png(mark_svg(), 512, STATIC / "icon-512.png")
        png(mark_svg(square=True), 512, STATIC / "icon-maskable-512.png", opaque=True)
        png(mark_svg(), 120, ROOT / "docs/brand/oauth-logo-120.png")

        sizes = [16, 32, 48]
        frames = [render(page, mark_svg(heavy=True), s) for s in sizes]
        buf = io.BytesIO()
        frames[-1].save(buf, "ICO", sizes=[(s, s) for s in sizes], append_images=frames[:-1])
        write(STATIC / "favicon.ico", buf.getvalue())

        og = STATIC / "og-image.png"
        og_image(page, og)
        print(og.relative_to(ROOT))
        browser.close()


if __name__ == "__main__":
    main()
