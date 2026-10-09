import copy

from mhs.data.importer import commit, prepare
from mhs.data.money import cents, to_cents, to_dollars


def test_money_round_trip():
    assert cents(1275.21) == 127521 and cents(0.1 + 0.2) == 30
    rec = {"billed": 1332.0, "lines": [{"patient_amount": 45.21}], "copays": {"specialist": 60}, "quantity": 2}
    assert to_cents(rec) == {"billed": 133200, "lines": [{"patient_amount": 4521}], "copays": {"specialist": 6000}, "quantity": 2}
    assert to_dollars(to_cents(rec))["lines"][0]["patient_amount"] == 45.21


def test_schema_error_names_the_record_and_blocks_saving(store, sample_data):
    bad = copy.deepcopy(sample_data)
    bad["documents"][0]["insurer_payed"] = 1
    del bad["documents"][0]["billed"]
    plan = prepare(bad, store, "x", None)
    assert not plan.ok
    assert any("eob-2026-02-10-pcp" in e and "billed" in e for e in plan.errors)
    assert any("insurer_payed" in e for e in plan.errors)


def test_reference_errors(store, sample_data):
    bad = copy.deepcopy(sample_data)
    bad["visits"][0]["provider_id"] = "prov-nobody"
    plan = prepare(bad, store, "x", None)
    assert plan.errors == ["visits (v-2026-02-10-pcp): provider_id 'prov-nobody' does not match any provider"]


def test_references_can_point_at_records_already_saved(loaded_store, config):
    docs_only = {"schema_version": "0.1", "documents": [
        {"id": "pay-new", "type": "payment", "date": "2026-10-01", "provider_id": "prov-derm",
         "account_id": "acct-hsa", "amount": 25}]}
    plan = prepare(docs_only, loaded_store, "x", None)
    assert plan.ok and plan.counts == {"documents": {"new": 1, "updated": 0, "unchanged": 0}}


def test_reimport_is_idempotent_and_counts_updates(loaded_store, config, sample_data):
    again = prepare(sample_data, loaded_store, "x", None)
    assert all(c["new"] == 0 and c["updated"] == 0 for c in again.counts.values())
    changed = copy.deepcopy(sample_data)
    changed["visits"][0]["description"] = "Changed"
    assert prepare(changed, loaded_store, "x", None).counts["visits"]["updated"] == 1


def test_attached_files_are_copied_and_missing_ones_warned(store, config, sample_data, tmp_path):
    folder = tmp_path / "in"
    (folder / "files").mkdir(parents=True)
    (folder / "files" / "eob-2026-02-10-pcp.pdf").write_bytes(b"%PDF-1.4 test")
    with_missing = copy.deepcopy(sample_data)
    with_missing["documents"][2]["file"] = "files/nope.pdf"
    plan = prepare(with_missing, store, "x", folder)
    assert plan.ok and plan.warnings == ["documents (eob-2026-04-02-pcp): file 'files/nope.pdf' not found"]
    commit(plan, store, config.documents_dir)
    saved = store.get("document", "eob-2026-02-10-pcp")
    assert saved["stored_file"] == "eob-2026-02-10-pcp.pdf" and saved["billed"] == 25000
    assert (config.documents_dir / "eob-2026-02-10-pcp.pdf").read_bytes() == b"%PDF-1.4 test"


def test_provider_notes_import(loaded_store):
    data = {"schema_version": "0.1", "provider_notes": [
        {"id": "n1", "provider_id": "prov-derm", "date": "2026-10-09", "channel": "phone", "text": "Called"}]}
    plan = prepare(data, loaded_store, "x", None)
    assert plan.ok and plan.counts == {"provider_notes": {"new": 1, "updated": 0, "unchanged": 0}}
    bad = {"schema_version": "0.1", "provider_notes": [{"id": "n1", "provider_id": "prov-nobody", "date": "2026-10-09", "text": "x"}]}
    assert prepare(bad, loaded_store, "x", None).errors == [
        "provider_notes (n1): provider_id 'prov-nobody' does not match any provider"]
