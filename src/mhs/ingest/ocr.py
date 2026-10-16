"""OCR adapter (ADR-029): photos and scanned PDFs become text with word boxes, in the application tier.

Engines: `tesseract` (the binary in the app image; keeps the stack offline) and `stub` (reads nothing, so the
member enters the fields by hand). Document AI Enterprise OCR joins in Google Cloud behind the same interface.
Word boxes are part of the result because scrubbing blanks identifiers on the image from them (PRV-04).
The app picks the engine from MHS_OCR_ENGINE (stack.py).
"""

import csv
import io
import shutil
import subprocess
from dataclasses import dataclass, field
from statistics import median
from typing import Protocol

PDF = "application/pdf"
HEIC = {"image/heic", "image/heif"}
RENDER_DPI = 300
MAX_PAGES = 20


class OcrUnavailable(RuntimeError):
    """The engine can't run here (not configured, or its binary is missing)."""


class UnreadableImage(ValueError):
    """The file can't be opened as an image; the message says why, in plain words."""


@dataclass(frozen=True)
class Word:
    text: str
    page: int
    box: tuple[float, float, float, float]  # left, top, right, bottom, as fractions of the page size
    confidence: float


@dataclass(frozen=True)
class OcrResult:
    text: str
    words: list[Word] = field(default_factory=list)
    engine: str = ""
    pages: list[str] = field(default_factory=list)

    @property
    def confidence(self) -> float:
        """Mean word confidence, 0 to 1 (0 when nothing was read)."""
        return round(sum(w.confidence for w in self.words) / len(self.words), 2) if self.words else 0.0


class OcrEngine(Protocol):
    name: str

    def read(self, data: bytes, content_type: str) -> OcrResult: ...


class StubOcr:
    """Reads nothing, so nothing silently passes unread documents along; the member types the fields."""

    name = "stub"

    def read(self, data: bytes, content_type: str) -> OcrResult:
        raise OcrUnavailable("OCR isn't configured on this server (MHS_OCR_ENGINE)")


def open_image(data: bytes, content_type: str):
    """A Pillow image, upright (EXIF rotation applied). HEIC photos are converted through pillow-heif."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    if content_type in HEIC:
        try:
            import pillow_heif
        except ImportError:  # pragma: no cover - pillow-heif is a dependency; this guards a broken install
            raise UnreadableImage("HEIC photos can't be read on this server. Export the photo as JPG and upload "
                                  "that.") from None
        pillow_heif.register_heif_opener()
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as e:
        raise UnreadableImage("This photo is damaged or in a format that can't be read. Upload a JPG or PNG.") from e
    return ImageOps.exif_transpose(image)


def page_images(data: bytes, content_type: str) -> list:
    """One image per page: a scanned PDF rendered at 300 DPI, or the photo itself."""
    if content_type != PDF:
        return [open_image(data, content_type)]
    import pypdfium2

    pdf = pypdfium2.PdfDocument(data)
    try:
        return [pdf[i].render(scale=RENDER_DPI / 72).to_pil() for i in range(min(len(pdf), MAX_PAGES))]
    finally:
        pdf.close()


class TesseractOcr:
    """Tesseract 5 through its command line (TSV output: one row per word with its box and confidence)."""

    name = "tesseract"

    def __init__(self, binary: str = "tesseract", lang: str = "eng", psm: int = 6, timeout: int = 120):
        self.binary = binary
        self.lang, self.psm, self.timeout = lang, psm, timeout

    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    def read(self, data: bytes, content_type: str) -> OcrResult:
        if not self.available():
            raise OcrUnavailable(f"the {self.binary!r} binary isn't installed")
        pages, words = [], []
        for number, image in enumerate(page_images(data, content_type), start=1):
            text, found = self._page(image, number)
            pages.append(text)
            words += found
        return OcrResult("\n\f\n".join(pages), words, self.name, pages)

    def _page(self, image, number: int) -> tuple[str, list[Word]]:
        buf = io.BytesIO()
        image.convert("L").save(buf, "PNG", dpi=(RENDER_DPI, RENDER_DPI))
        run = subprocess.run([self.binary, "stdin", "stdout", "-l", self.lang, "--psm", str(self.psm),
                              "--dpi", str(RENDER_DPI), "tsv"],
                             input=buf.getvalue(), capture_output=True, timeout=self.timeout, check=False)
        if run.returncode != 0:
            raise OcrUnavailable(f"tesseract failed ({run.returncode})")
        return tsv_to_text(run.stdout.decode("utf-8", "replace"), number, image.width, image.height)


def tsv_to_text(tsv: str, page: int, width: int, height: int) -> tuple[str, list[Word]]:
    """Rebuild the page's lines from Tesseract's words. A wide gap between two words on a line becomes three
    spaces, so label/value columns stay apart the way a PDF's text layer keeps them."""
    lines: dict[tuple, list[dict]] = {}
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        text = (row.get("text") or "").strip()
        if row.get("level") != "5" or not text or float(row.get("conf") or -1) < 0:
            continue
        key = (int(row["block_num"]), int(row["par_num"]), int(row["line_num"]))
        lines.setdefault(key, []).append({"text": text, "left": int(row["left"]), "top": int(row["top"]),
                                          "width": int(row["width"]), "height": int(row["height"]),
                                          "conf": float(row["conf"]) / 100})
    out, words = [], []
    for key in sorted(lines, key=lambda k: (min(w["top"] for w in lines[k]), k)):
        row = sorted(lines[key], key=lambda w: w["left"])
        char = median(w["width"] / max(1, len(w["text"])) for w in row)
        parts = []
        for i, w in enumerate(row):
            if i:
                gap = w["left"] - (row[i - 1]["left"] + row[i - 1]["width"])
                parts.append("   " if gap > 1.5 * char else " ")
            parts.append(w["text"])
            words.append(Word(w["text"], page, (round(w["left"] / width, 4), round(w["top"] / height, 4),
                                                round((w["left"] + w["width"]) / width, 4),
                                                round((w["top"] + w["height"]) / height, 4)), round(w["conf"], 2)))
        out.append("".join(parts))
    return "\n".join(out), words


ENGINES: dict[str, type] = {"stub": StubOcr, "tesseract": TesseractOcr}


def get_engine(name: str = "stub") -> OcrEngine:
    try:
        return ENGINES[name]()
    except KeyError:
        raise ValueError(f"unknown OCR engine {name!r}; known: {', '.join(ENGINES)}") from None
