"""Blank identifiers on page images from the OCR word boxes (PRV-04, ADR-029, TC-PRV-04-1).

The scrubber finds identifiers in the OCR text; every OCR word that is part of one is painted over on the page
image, so a scrubbed image can go where scrubbed text goes (the back-end tier, and AI extraction of images later).
Words are matched case-insensitively without punctuation; a word shared with a kept name (the insurer, a provider)
is blanked too, because hiding too much is the safe side.
"""

import re

from mhs.ingest.ocr import Word

PAD = 3  # pixels around each word box


def _norm(text: str) -> str:
    return re.sub(r"^[^\w@]+|[^\w@]+$", "", text).lower()


def identifier_words(found: list[tuple[str, str]]) -> set[str]:
    """The words making up the identifiers the scrubber replaced: (kind, text as printed) pairs."""
    words = set()
    for _kind, value in found:
        for w in re.split(r"[\s,]+", value):
            w = _norm(w)
            if len(w) >= 2:
                words.add(w)
    return words


def blank_pages(images: list, words: list[Word], targets: set[str]) -> tuple[list, int]:
    """Copies of the page images with every target word painted black. Returns (images, words blanked)."""
    from PIL import ImageDraw

    out = [im.convert("RGB").copy() for im in images]
    blanked = 0
    for w in words:
        if _norm(w.text) not in targets or not 1 <= w.page <= len(out):
            continue
        page = out[w.page - 1]
        left, top, right, bottom = w.box
        ImageDraw.Draw(page).rectangle(
            [left * page.width - PAD, top * page.height - PAD, right * page.width + PAD, bottom * page.height + PAD],
            fill="black")
        blanked += 1
    return out, blanked
