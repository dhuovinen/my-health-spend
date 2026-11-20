"""samples/walkthrough (docs/USER_TEST_GUIDE.md): imports on top of demo-setup's records, and each visit shows what
the guide says. Today is pinned to the middle of November 2026, when the guide's expectations were worked out."""

import json
from datetime import date
from pathlib import Path

from mhs.core import edits, estimate
from mhs.core.reconcile import build_report
from mhs.data import importer
from mhs.data.reference import load_tables
from mhs.data.repository import load_dataset
from mhs.data.store import Store
from mhs.ingest import learn
from mhs.ingest.extract import extract
from mhs.ingest.text import read_pdf
from mhs.ingest.worker import use_hints
from mhs.web.household.admin import demo_settings

HERE = Path(__file__).resolve().parents[1] / "samples" / "walkthrough"
TODAY = date(2026, 11, 14)


def household(tmp_path) -> Store:
    store = Store(tmp_path / "mhs.db")
    for kind, _, record in demo_settings():
        store.upsert(kind, record, edited=True)
    plan = importer.prepare(json.loads((HERE / "walkthrough-ingest.json").read_text()), store, "walkthrough", None)
    assert plan.ok, plan.errors
    assert plan.counts["visits"]["new"] == 12 and plan.counts["documents"]["new"] == 18
    importer.commit(plan, store, tmp_path / "docs")
    return store


def statuses(store) -> dict[str, str]:
    r = build_report(load_dataset(store), 2026, TODAY)
    return {v.id: v.status for v in r.visits if v.id.startswith("v-wt")}


def test_statuses_match_the_guide(tmp_path):
    store = household(tmp_path)
    assert statuses(store) == {
        "v-wt-01": "complete", "v-wt-02": "complete", "v-wt-03": "balance_outstanding",
        "v-wt-04": "balance_outstanding", "v-wt-05": "balance_outstanding", "v-wt-06": "discrepancy",
        "v-wt-07": "needs_review", "v-wt-08": "discrepancy", "v-wt-09": "complete", "v-wt-10": "awaiting_eob"}
    plan = store.get("plan", "plan-2026-granite-ppo")
    store.upsert("plan", {**plan, "terms_confirmed": True}, edited=True)  # step 3.6
    r = build_report(load_dataset(store), 2026, TODAY)
    assert {v: r.visit(v).at_stake for v in ("v-wt-03", "v-wt-04", "v-wt-05")} == \
        {"v-wt-03": 1500, "v-wt-04": 24000, "v-wt-05": 2500}
    store.upsert("document", edits.choose_version(store.get("document", "eob-wt-07-v2"), "use_newer"), edited=True)
    v = build_report(load_dataset(store), 2026, TODAY).visit("v-wt-07")
    assert [(c.kind, c.amount) for c in v.findings] == [("overpayment", 3000)]  # step 5.2


def test_plan_ahead_estimates(tmp_path):
    ds = load_dataset(household(tmp_path))
    found = {e.visit["id"]: e for e in (estimate.estimate(v, ds, TODAY, load_tables())
                                        for v in estimate.planned_visits(ds))}
    assert found["plan-wt-11"].total == 120000 and found["plan-wt-11"].cash.cheaper == "cash"  # without Part 1
    assert found["plan-wt-12"].total == 6000 and found["plan-wt-12"].past_due


def test_granite_eobs_are_learned_after_the_first(tmp_path):
    class Records(dict):
        def get(self, kind, rid):
            return dict.get(self, (kind, rid))

    records = Records()
    truth = [(41200, 28600, 22880, 5720), (39800, 27100, 21680, 5420), (33500, 24000, 19200, 4800)]
    fields = ("billed", "allowed", "insurer_paid", "patient_responsibility")
    for i, expected in enumerate(truth, 1):
        text = "\n".join(read_pdf((HERE / f"granite-eob-{i}.pdf").read_bytes()))
        result = extract(text).to_record()
        use_hints(result, text, records)
        got = tuple((result["fields"].get(k) or {}).get("value") for k in fields)
        assert got == ((None,) * 4 if i == 1 else expected), i
        made = [{"field": k, "confirmed": v} for k, v, g in zip(fields, expected, got) if g != v]
        hint = learn.learn(result, made, records.get(learn.HINT, learn.hint_id(result["layout_key"])))
        if hint:
            records[(learn.HINT, hint["id"])] = hint
