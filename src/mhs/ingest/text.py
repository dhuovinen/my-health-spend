"""Read an upload's text in the application tier (ADR-029, ADR-033): a PDF's own text layer, or OCR for a photo
or a scanned page.

Rejected files get a plain reason (TC-ING-01-5). Photos and pages without a text layer go to the OCR engine
(ingest/ocr.py); without one the member enters the fields by hand.
"""

import io
import logging
from dataclasses import dataclass

from mhs.ingest.ocr import OcrEngine, OcrUnavailable, UnreadableImage, get_engine, open_image

PDF = "application/pdf"
IMAGES = {"image/jpeg", "image/png", "image/heic", "image/heif", "image/webp"}
TEXT = {"text/html", "text/plain"}
EXTENSIONS = {".pdf": PDF, ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".heic": "image/heic",
              ".heif": "image/heif", ".webp": "image/webp", ".csv": "text/csv", ".xls": "application/vnd.ms-excel",
              ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
logging.getLogger("pypdf").setLevel(logging.ERROR)


class Unreadable(ValueError):
    """The upload can't be accepted; the message says why, in plain words."""


@dataclass(frozen=True)
class DocumentText:
    text: str  # empty when there is nothing machine-readable
    pages: int
    how: str  # how it was read, shown on the review page
    confidence: float = 1.0  # OCR's mean word confidence; 1.0 for a text layer
    words: tuple = ()  # OCR word boxes (ingest.ocr.Word), for blanking identifiers on the image (PRV-04)


def content_type(filename: str, declared: str) -> str:
    """Trust the extension over the browser's declared type, which varies (HEIC is often octet-stream)."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return EXTENSIONS.get(ext) or (declared or "").split(";")[0].strip().lower()


def read_pdf(data: bytes) -> list[str]:
    """Text of each page. Raises Unreadable for damaged or password-protected PDFs."""
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    if not data.startswith(b"%PDF"):
        raise Unreadable("This file isn't a PDF, though it's named like one.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                ok = reader.decrypt("")
            except Exception:  # noqa: BLE001
                ok = 0
            if not ok:
                raise Unreadable("This PDF is password-protected. Save a copy without the password and upload that.")
        return [page.extract_text() or "" for page in reader.pages]
    except Unreadable:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError) as e:
        raise Unreadable("This PDF is damaged and can't be read.") from e


def check_image(data: bytes, kind: str) -> None:
    """Refuse a photo that can't be opened before anything is stored."""
    try:
        open_image(data, kind)
    except UnreadableImage as e:
        raise Unreadable(str(e)) from e


def read_text(kind: str, data: bytes, ocr: OcrEngine | None = None) -> DocumentText:
    """The document's text. Pages without a text layer are read by OCR when an engine is available."""
    ocr = ocr or get_engine("stub")
    if kind == PDF:
        pages = read_pdf(data)
        if all(p.strip() for p in pages):
            return DocumentText("\n\f\n".join(pages), len(pages), "pdf text layer")
        try:
            result = ocr.read(data, PDF)
        except OcrUnavailable:
            text = "\n\f\n".join(pages)
            return DocumentText(text if text.strip() else "", len(pages), "scanned PDF: OCR not available")
        scanned = sum(1 for p in pages if not p.strip())
        merged = [p if p.strip() else (result.pages[i] if i < len(result.pages) else "") for i, p in enumerate(pages)]
        how = (f"scanned PDF, OCR ({result.engine})" if scanned == len(pages)
               else f"pdf text layer, {scanned} scanned page{'s' if scanned != 1 else ''} by OCR ({result.engine})")
        return DocumentText("\n\f\n".join(merged), len(pages), how, result.confidence, tuple(result.words))
    if kind in IMAGES:
        try:
            result = ocr.read(data, kind)
        except OcrUnavailable:
            return DocumentText("", 1, "photo: OCR not available")
        except UnreadableImage as e:
            raise Unreadable(str(e)) from e
        return DocumentText(result.text, 1, f"photo, OCR ({result.engine})", result.confidence, tuple(result.words))
    if kind in TEXT:  # a statement in the body of a forwarded email (ING-01, ADR-039)
        body = data.decode("utf-8", "replace")
        return DocumentText(html_to_text(body) if kind == "text/html" else body, 1, "email body")
    raise Unreadable("Only PDFs and photos (JPG, PNG, HEIC) can be read as documents.")


def html_to_text(html_text: str) -> str:
    """Readable lines from an HTML email: rows and paragraphs become lines, table cells stay apart like columns."""
    import html as html_lib
    import re

    t = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", html_text)
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h[1-6]|table)>", "\n", t)
    t = re.sub(r"(?i)</t[dh]>", "   ", t)
    t = html_lib.unescape(re.sub(r"<[^>]+>", " ", t)).replace("\u00a0", " ")
    lines = []
    for line in t.splitlines():
        cells = [re.sub(r"\s+", " ", c).strip() for c in re.split(r"\s{3,}", line)]
        if line := "   ".join(c for c in cells if c):
            lines.append(line)
    return "\n".join(lines)
