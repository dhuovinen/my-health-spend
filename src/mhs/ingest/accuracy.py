"""Extraction accuracy on a corpus with ground truth (PLT-02, TC-ING-02-1, TC-ING-03-1).

Each document goes the way an upload does: its text is read, identifiers are scrubbed to tokens (an in-memory
stand-in for the vault), the extractor classifies it and reads its fields, and tokens are mapped back before the
comparison. Measured before any member confirmation, as PLT-02 (A-01) defines it.
"""

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from mhs.ingest.extract import TYPES, extract
from mhs.ingest.scrub import Scrubber, normalize
from mhs.ingest.text import PDF, read_text
from mhs.vault.store import new_token

MONEY = {"billed", "adjustment", "allowed", "insurer_paid", "patient_responsibility", "balance_due"}
TARGET = 0.95


@dataclass
class Report:
    documents: int = 0
    types: Counter = field(default_factory=Counter)  # per true type: documents
    classified: Counter = field(default_factory=Counter)  # per true type: correctly classified
    confusion: list[tuple[str, str, str]] = field(default_factory=list)  # (document, truth, got)
    fields: dict = field(default_factory=lambda: defaultdict(lambda: [0, 0]))  # name -> [correct, total]
    misses: list[tuple[str, str, object, object]] = field(default_factory=list)  # (document, field, truth, got)

    @property
    def classification(self) -> float:
        return sum(self.classified.values()) / self.documents if self.documents else 0.0

    def rate(self, names) -> float:
        correct = sum(self.fields[n][0] for n in names if n in self.fields)
        total = sum(self.fields[n][1] for n in names if n in self.fields)
        return correct / total if total else 0.0

    @property
    def amounts(self) -> float:
        return self.rate(MONEY)

    @property
    def headers(self) -> float:
        return self.rate(list(self.fields))

    def markdown(self) -> str:
        out = [f"Documents: {self.documents}", "",
               "| Measure | Result | Target |", "| --- | --- | --- |",
               f"| Classification (TC-ING-02-1) | {self.classification:.1%} | {TARGET:.0%} |",
               f"| Amounts correct before confirmation (PLT-02) | {self.amounts:.1%} | {TARGET:.0%} |",
               f"| All header fields (TC-ING-03-1) | {self.headers:.1%} | |", "",
               "| Type | Documents | Classified correctly |", "| --- | --- | --- |"]
        for t in TYPES:
            if self.types[t]:
                out.append(f"| {t} | {self.types[t]} | {self.classified[t]} |")
        out += ["", "| Field | Correct | Of |", "| --- | --- | --- |"]
        for name, (correct, total) in sorted(self.fields.items()):
            out.append(f"| {name} | {correct} | {total} |")
        if self.confusion:
            out += ["", "Misclassified: " + "; ".join(f"{d} ({t} read as {g})" for d, t, g in self.confusion)]
        if self.misses:
            out += ["", "Field misses:"] + [f"- {d} {n}: expected {t!r}, got {g!r}" for d, n, t, g in self.misses]
        return "\n".join(out)


def _same(name: str, truth, got) -> bool:
    if got is None:
        return False
    if name in ("patient",):
        return normalize("name", str(truth)) == normalize("name", str(got))
    if name in ("provider",):
        return " ".join(str(truth).lower().split()) == " ".join(str(got).lower().split())
    if name in ("account_number", "claim_number"):
        return normalize("member_id", str(truth)) == normalize("member_id", str(got))
    return truth == got


def evaluate(corpus: Path, extractor: Callable = extract, known_names: tuple[str, ...] = ()) -> Report:
    report = Report()
    for truth_file in sorted(Path(corpus).glob("*.json")):
        truth = json.loads(truth_file.read_text())
        doc = truth_file.stem
        text = read_text(PDF, (truth_file.with_suffix(".pdf")).read_bytes()).text
        vault: dict[tuple[str, str], str] = {}
        scrubbed = Scrubber(lambda kind, value: vault.setdefault((kind, value), new_token()), list(known_names)).scrub(text)
        values = {token: value for (kind, value), token in vault.items()}
        x = extractor(scrubbed.text)
        report.documents += 1
        report.types[truth["doc_type"]] += 1
        if x.doc_type == truth["doc_type"]:
            report.classified[truth["doc_type"]] += 1
        else:
            report.confusion.append((doc, truth["doc_type"], x.doc_type))
        for name, expected in truth["fields"].items():
            got = x.fields.get(name).value if name in x.fields else None
            if isinstance(got, str) and got.startswith("tok_"):
                got = values.get(got, got)
            report.fields[name][1] += 1
            if _same(name, expected, got):
                report.fields[name][0] += 1
            else:
                report.misses.append((doc, name, expected, got))
    return report
