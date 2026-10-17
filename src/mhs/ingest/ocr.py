"""OCR adapter (ADR-029): photos and scanned PDFs become text with word boxes, in the application tier.

Engines: `tesseract` (the binary in the app image; keeps the stack offline), `documentai` (Document AI Enterprise
OCR in Google Cloud, ADR-036) and `stub` (reads nothing, so the member enters the fields by hand).
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


class DocumentAiOcr:
    """Document AI (Enterprise Document OCR) over its REST API (ADR-029, ADR-036). Keeps photos and scans inside
    the Google Cloud project and BAA. MHS_DOCAI_PROCESSOR names the processor
    (projects/<p>/locations/<us|eu>/processors/<id>); MHS_DOCAI_ENDPOINT points elsewhere in tests."""

    name = "documentai"
    TYPES = {PDF, "image/jpeg", "image/png", "image/webp", "image/tiff", "image/gif", "image/bmp"}

    def __init__(self, processor: str | None = None, http=None, token=None, endpoint: str | None = None):
        import os

        self.processor = processor or os.environ.get("MHS_DOCAI_PROCESSOR", "")
        location = self.processor.split("/locations/")[1].split("/")[0] if "/locations/" in self.processor else "us"
        self.endpoint = (endpoint or os.environ.get("MHS_DOCAI_ENDPOINT")
                         or f"https://{location}-documentai.googleapis.com").rstrip("/")
        self._http, self._token = http, token

    def read(self, data: bytes, content_type: str) -> OcrResult:
        import base64

        import httpx

        from mhs.data.gcp import GoogleError, default_token

        if not self.processor:
            raise OcrUnavailable("Document AI isn't configured on this server (MHS_DOCAI_PROCESSOR)")
        if content_type not in self.TYPES:  # HEIC and anything else Document AI doesn't take: send it as JPEG
            buf = io.BytesIO()
            open_image(data, content_type).convert("RGB").save(buf, "JPEG", quality=92)
            data, content_type = buf.getvalue(), "image/jpeg"
        http = self._http or httpx.Client(timeout=120)
        token = self._token or default_token(emulated="googleapis.com" not in self.endpoint)
        r = http.post(f"{self.endpoint}/v1/{self.processor}:process",
                      json={"rawDocument": {"content": base64.b64encode(data).decode(), "mimeType": content_type},
                            "skipHumanReview": True},
                      headers={"Authorization": f"Bearer {token.token()}"})
        if r.status_code >= 400:
            raise GoogleError(f"document ai process failed: HTTP {r.status_code}")
        return documentai_result(r.json().get("document", {}))


def _anchor_text(text: str, layout: dict) -> str:
    segments = (layout.get("textAnchor") or {}).get("textSegments") or []
    return "".join(text[int(s.get("startIndex", 0)):int(s.get("endIndex", 0))] for s in segments)


def documentai_result(document: dict) -> OcrResult:
    """A Document AI `Document` as text with word boxes (fractions of the page) and confidences."""
    text = document.get("text", "")
    pages, words = [], []
    for number, page in enumerate(document.get("pages", []), start=1):
        layout = page.get("layout") or {}
        pages.append(_anchor_text(text, layout).strip("\n") if layout.get("textAnchor") else "")
        for tok in page.get("tokens", []):
            tl = tok.get("layout") or {}
            word = _anchor_text(text, tl).strip()
            vertices = (tl.get("boundingPoly") or {}).get("normalizedVertices") or []
            if not word or not vertices:
                continue
            xs, ys = [v.get("x", 0.0) for v in vertices], [v.get("y", 0.0) for v in vertices]
            words.append(Word(word, number, (round(min(xs), 4), round(min(ys), 4), round(max(xs), 4),
                                             round(max(ys), 4)), round(float(tl.get("confidence", 0.0)), 2)))
    if not pages:
        pages = [text]
    return OcrResult("\n\f\n".join(pages) if any(pages) else text, words, "documentai", pages)


ENGINES: dict[str, type] = {"stub": StubOcr, "tesseract": TesseractOcr, "documentai": DocumentAiOcr}


def get_engine(name: str = "stub") -> OcrEngine:
    try:
        return ENGINES[name]()
    except KeyError:
        raise ValueError(f"unknown OCR engine {name!r}; known: {', '.join(ENGINES)}") from None
