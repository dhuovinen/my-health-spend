"""Read an upload's text in the application tier (ADR-029, ADR-033): a PDF's own text layer, or OCR for a photo.

Rejected files get a plain reason (TC-ING-01-5). Photos go to the OCR engine; until one is configured the
member enters the fields by hand.
"""

import io
import logging

from mhs.ingest.ocr import OcrEngine, get_engine

PDF = "application/pdf"
IMAGES = {"image/jpeg", "image/png", "image/heic", "image/heif", "image/webp"}
EXTENSIONS = {".pdf": PDF, ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".heic": "image/heic",
              ".heif": "image/heif", ".webp": "image/webp", ".csv": "text/csv", ".xls": "application/vnd.ms-excel",
              ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
logging.getLogger("pypdf").setLevel(logging.ERROR)


class Unreadable(ValueError):
    """The upload can't be accepted; the message says why, in plain words."""


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


def read_text(kind: str, data: bytes, ocr: OcrEngine | None = None) -> tuple[str, int, str]:
    """(text, page count, how it was read). Text is empty when there is nothing machine-readable yet."""
    if kind == PDF:
        pages = read_pdf(data)
        text = "\n\f\n".join(pages)
        if text.strip():
            return text, len(pages), "pdf text layer"
        return "", len(pages), "scanned PDF: needs OCR"
    if kind in IMAGES:
        try:
            result = (ocr or get_engine()).read(data, kind)
        except NotImplementedError:
            return "", 1, "photo: OCR not configured"
        return result.text, 1, f"OCR ({result.engine})"
    raise Unreadable("Only PDFs and photos (JPG, PNG, HEIC) can be read as documents.")
