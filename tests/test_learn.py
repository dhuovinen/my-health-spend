"""ING-06 (ADR-051): corrections on one layout improve the next documents of that layout, and only that layout."""

import random

from mhs.ingest import learn
from mhs.ingest.extract import extract
from mhs.ingest.worker import use_hints

FIELDS = ("billed", "allowed", "insurer_paid", "patient_responsibility")


def granite(rng: random.Random) -> tuple[str, dict]:
    """An EOB layout with labels the rules weren't written for."""
    billed = rng.randint(20000, 90000)
    allowed = billed - rng.randint(5000, 15000)
    owes = rng.randint(0, allowed // 3)
    truth = {"billed": billed, "allowed": allowed, "insurer_paid": allowed - owes, "patient_responsibility": owes}
    text = (f"GRANITE MUTUAL\nExplanation of Benefits - this is not a bill\nClaim ref: GM{rng.randint(10000, 99999)}\n"
            f"Submitted by provider ${billed / 100:,.2f}\nContracted rate ${allowed / 100:,.2f}\n"
            f"Granite remitted ${(allowed - owes) / 100:,.2f}\nMember portion ${owes / 100:,.2f}\n")
    return text, truth


def errors(result: dict, truth: dict) -> int:
    return sum((result["fields"].get(k) or {}).get("value") != truth[k] for k in FIELDS)


class Records:
    def __init__(self):
        self.rows = {}

    def get(self, kind, rid):
        return self.rows.get((kind, rid))

    def put(self, kind, rec):
        self.rows[(kind, rec["id"])] = rec


def read(text: str, records: Records) -> dict:
    result = extract(text).to_record()
    use_hints(result, text, records)
    return result


def correct(result: dict, truth: dict, records: Records) -> None:
    """What the review page does on confirm: the corrections, then the labels behind them."""
    made = [{"field": k, "confirmed": truth[k]} for k in FIELDS if result["fields"].get(k, {}).get("value") != truth[k]]
    hint = learn.learn(result, made, records.get(learn.HINT, learn.hint_id(result["layout_key"])))
    if hint:
        records.put(learn.HINT, hint)


def test_tc_ing_06_1_error_rate_halves_on_the_next_five():
    rng, records = random.Random(6), Records()
    docs = [granite(rng) for _ in range(7)]
    first = [read(t, records) for t, _ in docs[:2]]
    before = sum(errors(r, truth) for r, (_, truth) in zip(first, docs[:2])) / (2 * len(FIELDS))
    assert before > 0.5  # the rules miss this layout's labels
    for r, (_, truth) in zip(first, docs[:2]):
        correct(r, truth, records)
    after_docs = [read(t, records) for t, _ in docs[2:]]
    after = sum(errors(r, truth) for r, (_, truth) in zip(after_docs, docs[2:])) / (5 * len(FIELDS))
    assert after <= before / 2
    assert all(r.get("learned_fields") for r in after_docs)
    assert all(r["fields"]["allowed"]["confidence"] == learn.LEARNED for r in after_docs)


def test_tc_ing_06_2_other_layouts_unchanged():
    rng, records = random.Random(7), Records()
    text, truth = granite(rng)
    correct(read(text, records), truth, records)
    other = text.replace("GRANITE MUTUAL", "BLUEWATER HEALTH PLAN")
    plain = extract(other).to_record()
    with_hints = read(other, records)
    assert not with_hints.get("learned_fields")
    assert {k: plain["fields"][k]["value"] for k in FIELDS} == {k: with_hints["fields"][k]["value"] for k in FIELDS}


def test_ambiguous_values_teach_nothing():
    ext = {"layout_key": "eob:x", "value_labels": {"5000": ["Copay", "Member portion"]}}
    assert learn.learn(ext, [{"field": "patient_responsibility", "confirmed": 5000}]) is None


def test_labels_drop_tokens():
    labels = learn.value_labels("Paid for tok_name_1 Member portion: $12.00\n")
    assert labels == {"1200": ["Paid for Member portion"]}
