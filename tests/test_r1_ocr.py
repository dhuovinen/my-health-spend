"""OCR in the application tier (ADR-029): Tesseract's words become lines and boxes; scanned pages, photos and
iPhone HEIC photos are read; damaged photos are refused with a plain reason. Tests that need the tesseract binary
skip without it (the compose tests runner has it)."""

import io
import shutil

import pytest

from mhs.ingest.extract import extract
from mhs.ingest.ocr import OcrResult, OcrUnavailable, TesseractOcr, open_image, tsv_to_text
from mhs.ingest.text import PDF, Unreadable, check_image, read_text
from mhs.ingest.worker import cap_confidence
from tests.pdfs import make_image, make_pdf, make_scanned_pdf, render_text
from tests.test_r1_scenarios import EOB, STATEMENT

needs_tesseract = pytest.mark.skipif(not shutil.which("tesseract"), reason="tesseract isn't installed here")
HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"


def word(line: int, left: int, text: str, conf: float = 96.0, top: int = 100) -> str:
    return f"5\t1\t1\t1\t{line}\t1\t{left}\t{top + 40 * line}\t{12 * len(text)}\t30\t{conf}\t{text}\n"


class FakeOcr:
    """Reads every page as 'OCR page n'."""

    name = "fake"

    def read(self, data: bytes, content_type: str) -> OcrResult:
        pages = [f"OCR page {i}" for i in range(1, 3)]
        return OcrResult("\n\f\n".join(pages), [], self.name, pages)


def test_tsv_becomes_lines_with_column_gaps_and_boxes():
    tsv = HEADER + word(1, 10, "Patient:") + word(1, 120, "Pat") + word(1, 170, "Example") + \
        word(1, 600, "Member") + word(2, 10, "Plan") + word(2, 70, "paid:") + word(2, 140, "$155.00", conf=80) + \
        "1\t1\t0\t0\t0\t0\t0\t0\t1000\t1000\t-1\t\n" + word(3, 10, " ", conf=-1)
    text, words = tsv_to_text(tsv, page=1, width=1000, height=2000)
    assert text == "Patient: Pat Example   Member\nPlan paid: $155.00"
    assert len(words) == 7 and words[0].box == (0.01, 0.07, 0.106, 0.085) and words[6].confidence == 0.8
    assert all(0 <= v <= 1 for w in words for v in w.box)


def test_scanned_pages_go_to_ocr_and_text_layers_stay():
    scanned = make_scanned_pdf("one", "two")
    assert read_text(PDF, scanned).how == "scanned PDF: OCR not available"  # stub engine: typed by hand
    doc = read_text(PDF, scanned, FakeOcr())
    assert doc.text == "OCR page 1\n\f\nOCR page 2" and doc.pages == 2 and doc.how == "scanned PDF, OCR (fake)"
    doc = read_text(PDF, make_pdf("Typed page", "Also typed"), FakeOcr())
    assert doc.how == "pdf text layer" and "OCR" not in doc.text and doc.confidence == 1.0


def test_photo_without_an_engine_is_typed_by_hand():
    doc = read_text("image/png", make_image("hello"))
    assert doc.text == "" and doc.how == "photo: OCR not available"


def test_heic_is_converted_and_exif_rotation_applied():
    assert open_image(make_image("hello", "HEIC"), "image/heic").size == render_text("hello").size
    from PIL import Image

    buf, image = io.BytesIO(), render_text("hello")
    exif = Image.Exif()
    exif[0x0112] = 6  # stored sideways: the camera says "rotate 90 degrees"
    image.save(buf, "JPEG", exif=exif)
    assert open_image(buf.getvalue(), "image/jpeg").size == (image.height, image.width)


def test_damaged_photos_are_refused_plainly():
    for data, kind in ((b"\xff\xd8\xff nope", "image/jpeg"), (b"ftypheic nope", "image/heic"), (b"", "image/png")):
        with pytest.raises(Unreadable, match="damaged or in a format"):
            check_image(data, kind)


def test_missing_binary_is_reported_not_crashed():
    with pytest.raises(OcrUnavailable):
        TesseractOcr(binary="no-such-tesseract").read(make_image("x"), "image/png")
    assert read_text("image/png", make_image("x"), TesseractOcr(binary="no-such-tesseract")).text == ""


def test_ocr_confidence_caps_field_confidence():
    result = extract(EOB).to_record()
    cap_confidence(result, 0.7)
    assert max(f["confidence"] for f in result["fields"].values()) == 0.7 and result["type_confidence"] <= 0.7
    untouched = extract(EOB).to_record()
    cap_confidence(untouched, 1.0)
    assert untouched == extract(EOB).to_record()


@needs_tesseract
@pytest.mark.parametrize("fmt,kind", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("HEIC", "image/heic")])
def test_tesseract_reads_a_photo_of_an_eob(fmt, kind):
    result = TesseractOcr().read(make_image(EOB, fmt), kind)
    x = extract(result.text)
    assert x.doc_type == "eob" and x.fields["billed"].value == 32000 and x.fields["allowed"].value == 20000
    assert "Patient: Pat Example   Member ID" in result.text  # the column gap survives
    assert result.confidence > 0.8 and result.words and result.engine == "tesseract"
    assert all(w.page == 1 and 0 <= w.box[0] < w.box[2] <= 1 and 0 <= w.box[1] < w.box[3] <= 1 for w in result.words)


@needs_tesseract
def test_tesseract_reads_a_scanned_two_page_pdf():
    doc = read_text(PDF, make_scanned_pdf(STATEMENT, EOB), TesseractOcr())
    assert doc.pages == 2 and doc.how == "scanned PDF, OCR (tesseract)"
    first, second = doc.text.split("\n\f\n")
    assert "Amount due: $320.00" in first and "THIS IS NOT A BILL" in second
