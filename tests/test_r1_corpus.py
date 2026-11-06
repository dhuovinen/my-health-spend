"""The extraction corpus and accuracy run (PLT-02, TC-ING-02-1, TC-ING-03-1). No database.

tests/corpus/ is the development set the layout rules were fixed against: it must stay at the targets.
tests/corpus-holdout/ was never used to tune them; its result is the honest PLT-02 figure, recorded in TESTING.md,
and here it may only go up.
"""

import json
from collections import Counter
from pathlib import Path

import pytest

from mhs.ingest.accuracy import TARGET, evaluate
from mhs.ingest.extract import TYPES

HERE = Path(__file__).parent
DEV, HOLDOUT = HERE / "corpus", HERE / "corpus-holdout"
# The held-out baseline for the layout rules, measured 2026-10-16 (TESTING.md "Extraction accuracy").
HOLDOUT_BASELINE = {"classification": 40 / 50, "amounts": 40 / 65, "headers": 70 / 160}


@pytest.mark.parametrize("corpus", [DEV, HOLDOUT], ids=["development", "holdout"])
def test_corpus_covers_every_type(corpus):
    """TEST_PLAN "Extraction corpus": at least 5 documents per ING-02 type, each with ground truth."""
    truths = [json.loads(p.read_text()) for p in corpus.glob("*.json")]
    counts = Counter(t["doc_type"] for t in truths)
    assert set(counts) == set(TYPES) and min(counts.values()) >= 5, counts
    assert all(p.with_suffix(".pdf").exists() for p in corpus.glob("*.json"))
    for t in truths:
        if t["doc_type"] in ("eob", "provider_statement", "itemized_bill"):
            assert {"patient", "provider"} <= set(t["fields"]), t


def test_holdout_is_big_enough_for_plt_02():
    assert len(list(HOLDOUT.glob("*.json"))) >= 50  # PLT-02 (A-01): a held-out sample of at least 50


def test_development_corpus_meets_the_targets():
    report = evaluate(DEV)
    assert report.classification >= TARGET, report.markdown()
    assert report.amounts >= TARGET, report.markdown()
    assert report.headers >= TARGET, report.markdown()


def test_holdout_does_not_fall_below_its_baseline():
    """The layout rules don't generalize to unseen wording (TESTING.md); this only guards against getting worse."""
    report = evaluate(HOLDOUT)
    assert report.classification >= HOLDOUT_BASELINE["classification"], report.markdown()
    assert report.amounts >= HOLDOUT_BASELINE["amounts"] - 1e-9, report.markdown()
    assert report.headers >= HOLDOUT_BASELINE["headers"] - 1e-9, report.markdown()


def test_corpus_is_reproducible(tmp_path, monkeypatch):
    """The generator is seeded: regenerating gives the same documents and ground truth."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("make_corpus", HERE.parent / "tools" / "make_corpus.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "OUT", tmp_path / "corpus")
    mod.main()
    for corpus in (DEV, HOLDOUT):
        regenerated = tmp_path / corpus.name
        for truth in corpus.glob("*.json"):
            assert (regenerated / truth.name).read_text() == truth.read_text(), truth.name
