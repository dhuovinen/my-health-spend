"""OCR adapter (ADR-029). Interface only in phase 1.1.

Phase 1.3 adds the engines: Tesseract in the worker image locally, Document AI Enterprise OCR in Google Cloud.
Word boxes are part of the result because scrubbing blanks identifiers on the image from them (PRV-04).
"""

from dataclasses import dataclass, field
from typing import Protocol


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


class OcrEngine(Protocol):
    name: str

    def read(self, data: bytes, content_type: str) -> OcrResult: ...


class StubOcr:
    """Placeholder until phase 1.3: refuses to read, so nothing silently passes unread documents along."""

    name = "stub"

    def read(self, data: bytes, content_type: str) -> OcrResult:
        raise NotImplementedError("OCR arrives in phase 1.3 (Tesseract locally, Document AI in Google Cloud)")


ENGINES: dict[str, type] = {"stub": StubOcr}


def get_engine(name: str = "stub") -> OcrEngine:
    try:
        return ENGINES[name]()
    except KeyError:
        raise ValueError(f"unknown OCR engine {name!r}; known: {', '.join(ENGINES)}") from None
