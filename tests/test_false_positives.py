"""PLT-02 false-positive tracking (TC-PLT-02-2, test plan A-01, ADR-044): the member says whether each finding they
close was a real problem or wrong; the rate is wrong over decided, per kind and overall, per period and release.
The pages run against both apps through the `web` fixture; the owner's report against Postgres."""

import json
import re

import pytest

from mhs import RELEASE
from mhs.core import edits
from mhs.core.accuracy import TARGET, accuracy, open_findings, percent
from mhs.core.reconcile import Check
from mhs.data.household_store import HouseholdStore
from tests.conftest import SAMPLE
from tests.test_web import import_sample, web  # noqa: F401 (fixture)

PCP = "v-2026-04-02-pcp"  # the sample's visit with two findings: C2 missed adjustment and C4 overpayment, $80.00


def text_of(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).replace("&#39;", "'")


def closed(code, verdict=None, when="2026-10-05", kind="", release=RELEASE, amount=1000):
    entry = {"code": code, "amount": amount, "closed": when, "how": "marked dealt with"}
    entry.update({k: v for k, v in (("verdict", verdict), ("kind", kind), ("release", release)) if v})
    return entry


def visits_with(*entries) -> list[dict]:
    return [{"id": f"v{n}", "date": "2026-09-01", "closed_findings": [e]} for n, e in enumerate(entries)]


# ---------- the rate (core) ----------

def test_plt_02_2_rate_is_wrong_over_decided_per_kind_and_overall():
    """TC-PLT-02-2: 1 of 20 decided findings marked wrong is 5.0%, inside the 5% ceiling; a second makes it 9.5%."""
    entries = [closed("C2", "real", kind="missed_adjustment") for _ in range(12)]
    entries += [closed("C4", "real", kind="overpayment") for _ in range(7)]
    entries += [closed("C2", "wrong", kind="missed_adjustment")]
    acc = accuracy(visits_with(*entries))
    t = acc.total
    assert (t.real, t.wrong, t.decided) == (19, 1, 20)
    assert t.rate == pytest.approx(0.05) and t.meets_target and percent(t.rate) == "5.0%"
    by_kind = {k.key: k for k in acc.rows}
    assert by_kind["missed_adjustment"].label == "Missed adjustment"
    assert (by_kind["missed_adjustment"].real, by_kind["missed_adjustment"].wrong) == (12, 1)
    assert by_kind["overpayment"].rate == 0 and by_kind["overpayment"].meets_target
    assert [k.key for k in acc.rows] == ["missed_adjustment", "overpayment"]  # most decided first
    worse = accuracy(visits_with(*entries, closed("C3", "wrong")))
    assert worse.total.rate == pytest.approx(2 / 21) and not worse.total.meets_target
    assert {k.key: k.label for k in worse.rows}["C3"] == "Network status agrees"  # a check without kinds: its code
    assert TARGET == 0.05


def test_plt_02_2_open_and_unrated_findings_are_beside_the_rate_not_in_it():
    acc = accuracy(visits_with(closed("C2", "real", kind="missed_adjustment"), closed("C2", None, release="")),
                   [Check("C2", "fail", "", 500, "missed_adjustment"), Check("C4", "fail", "", 500, "overpayment")])
    t = acc.total
    assert (t.decided, t.unrated, t.open, t.rate) == (1, 1, 2, 0)
    assert accuracy([]).total.rate is None and accuracy([]).total.meets_target is None
    assert not accuracy(visits_with(closed("C6", "real"), closed("claim_filed", "real"))).rows  # not findings of error
    assert percent(None) == "–"


def test_plt_02_2_period_and_release():
    """Per release: only the closings in the period count (both ends included), for one release or all."""
    acc = accuracy(visits_with(closed("C2", "wrong", "2026-09-30"), closed("C2", "real", "2026-10-01"),
                               closed("C2", "real", "2026-10-31"), closed("C2", "wrong", "2026-11-01"),
                               closed("C2", "wrong", "2026-10-15", release="release-2")),
                   start="2026-10-01", end="2026-10-31")
    assert (acc.total.real, acc.total.wrong) == (2, 1) and acc.releases == {RELEASE: 2, "release-2": 1}
    one = accuracy(visits_with(closed("C2", "real"), closed("C2", "wrong", release="release-2")), release=RELEASE)
    assert (one.total.real, one.total.wrong) == (1, 0)
    both = one + accuracy(visits_with(closed("C2", "wrong")))  # adding households
    assert (both.total.real, both.total.wrong, both.releases) == (1, 1, {RELEASE: 2})


def test_plt_02_2_open_findings_leave_out_what_the_member_cannot_close():
    class V:
        def __init__(self, checks):
            self.findings = checks

    class R:
        visits = [V([Check("C2", "fail", kind="missed_adjustment"), Check("C6", "fail"),
                     Check("claim_filed", "fail", kind="not_filed")])]

    assert [c.code for c in open_findings([R()])] == ["C2"]


# ---------- the member's verdict (core/edits) ----------

def test_closing_keeps_the_verdict_reason_kind_and_release():
    visit = {"id": "v1", "date": "2026-09-01"}
    out = edits.close_finding(visit, "C2", 8000, "2026-10-18", "marked wrong", "wrong",
                              "  The adjustment   was on page 2 " + "x" * 300, "missed_adjustment", RELEASE)
    entry = out["closed_findings"][0]
    assert entry["verdict"] == "wrong" and entry["kind"] == "missed_adjustment" and entry["release"] == RELEASE
    assert entry["reason"].startswith("The adjustment was on page 2 x") and len(entry["reason"]) == 200
    assert "closed_findings" not in visit  # a copy, not a change in place
    assert "closed_findings" not in edits.reopen_finding(out, "C2", 8000)  # reopening drops the verdict too
    with pytest.raises(edits.EditError, match="real problem or wrong"):
        edits.close_finding(visit, "C2", 8000, "2026-10-18", verdict="maybe")



@pytest.mark.parametrize("result, verdict", [("findings_wrong", "wrong"), ("refunded", "real"), ("corrected", "real"),
                                             ("written_off", "real"), ("denied", None)])
def test_plt_02_2_a_resolved_case_gives_its_findings_a_verdict(result, verdict):
    """A dispute case's outcome is the member's word on its findings: fixed in any way, real; "the findings were
    wrong", wrong; denied doesn't say, so they stay unrated (ADR-044 with ADR-042). A balance owed is never rated."""
    visit = {"id": "v1", "date": "2026-09-01"}
    findings = [{"code": "C2", "amount": 8000, "kind": "missed_adjustment"}, {"code": "C6", "amount": 5000}]
    opened, case_id = edits.open_case(visit, "2026-10-01", findings)
    done = edits.resolve_case(opened, case_id, "2026-10-18", result, 8000, release=RELEASE)
    c2, c6 = done["closed_findings"]
    assert c2["how"].startswith("case resolved") and c2.get("verdict") == verdict
    assert c2["kind"] == "missed_adjustment" and c2.get("release") == (RELEASE if verdict else None)
    assert "verdict" not in c6
    assert done["cases"][0]["outcome"]["recovered"] == (0 if result in ("findings_wrong", "denied") else 8000)
    assert "closed_findings" not in edits.reopen_case(done, case_id, "2026-10-19")  # reopening drops the verdicts


# ---------- on the pages, both apps ----------

def test_plt_02_2_member_marks_a_finding_wrong_and_sees_the_rate(web):
    """TC-PLT-02-2 end to end: closing asks real or wrong with an optional reason; the verdict is a member edit that a
    re-import keeps (ADR-011); Finding accuracy shows the rate per kind and overall."""
    import_sample(web)
    page = web.client.get(f"/visits/{PCP}").text
    assert "It was a real problem" in page and "It was wrong" in page and 'name="reason"' in page
    assert 'href="/accuracy"' in page

    # Nothing decided yet: both findings are open, beside the rate.
    page = text_of(web.client.get("/accuracy").text)
    assert "Finding accuracy" in page and "Nothing decided yet" in page
    assert re.search(r"All findings 0 0 – 2", page)

    # Without a verdict, or for a finding that isn't open, nothing is saved.
    r = web.client.post(f"/visits/{PCP}/findings", data={"code": "C2", "amount": "8000"})
    assert r.status_code == 400 and "real problem or wrong" in r.text
    r = web.client.post(f"/visits/{PCP}/findings", data={"code": "C2", "amount": "7999", "verdict": "wrong"})
    assert r.status_code == 400 and "isn't open" in text_of(r.text)
    assert not web.store.get("visit", PCP).get("closed_findings")

    web.client.post(f"/visits/{PCP}/findings", data={"code": "C2", "amount": "8000", "verdict": "wrong",
                                                     "reason": "The EOB was for another visit"})
    web.client.post(f"/visits/{PCP}/findings", data={"code": "C4", "amount": "8000", "verdict": "real"})
    entries = {f["code"]: f for f in web.store.get("visit", PCP)["closed_findings"]}
    assert entries["C2"]["verdict"] == "wrong" and entries["C2"]["kind"] == "missed_adjustment"
    assert entries["C2"]["reason"] == "The EOB was for another visit" and entries["C2"]["release"] == RELEASE
    assert entries["C4"]["verdict"] == "real" and entries["C4"]["kind"] == "overpayment"
    assert PCP in web.store.edited_ids("visit")

    page = text_of(web.client.get(f"/visits/{PCP}").text)
    assert "marked wrong): The EOB was for another visit" in page and "(marked dealt with)" in page

    page = text_of(web.client.get("/accuracy").text)
    assert re.search(r"Missed adjustment 0 1 100\.0% 0", page) and re.search(r"Overpayment 1 0 0\.0% 0", page)
    assert re.search(r"All findings 1 1 50\.0% 0", page) and "Above the 5% aim" in page
    assert "another visit" not in page  # reasons stay on the visit page

    # Re-importing the same file keeps the member's verdicts (ADR-011).
    import_sample(web)
    assert {f["code"]: f["verdict"] for f in web.store.get("visit", PCP)["closed_findings"]} == \
        {"C2": "wrong", "C4": "real"}

    # Reopening takes a finding out of the rate again.
    web.client.post(f"/visits/{PCP}/findings", data={"code": "C2", "amount": "8000", "action": "reopen"})
    assert re.search(r"All findings 1 0 0\.0% 1", text_of(web.client.get("/accuracy").text))


def test_plt_02_2_resolving_a_case_says_real_or_wrong(web):
    import_sample(web)
    r = web.client.post(f"/visits/{PCP}/cases", data={"finding": "all"}, follow_redirects=False)
    case_url = r.headers["location"]
    assert "The findings were wrong" in web.client.get(case_url).text
    web.client.post(f"{case_url}/resolve", data={"result": "findings_wrong", "recovered": ""})
    visit = web.store.get("visit", PCP)
    how = "case resolved: the findings were wrong"
    assert {(f["code"], f["verdict"], f["how"]) for f in visit["closed_findings"]} == {("C2", "wrong", how),
                                                                                       ("C4", "wrong", how)}
    assert visit["cases"][0]["outcome"]["recovered"] == 0
    assert re.search(r"All findings 0 2 100\.0%", text_of(web.client.get("/accuracy").text))

    web.client.post(f"{case_url}/reopen", data={})
    assert "closed_findings" not in web.store.get("visit", PCP)
    web.client.post(f"{case_url}/resolve", data={"result": "refunded", "recovered": "80.00"})
    assert {f["verdict"] for f in web.store.get("visit", PCP)["closed_findings"]} == {"real"}


def test_findings_closed_before_the_question_are_not_rated(web, tmp_path):
    """An ingest file (or a Release 0 database) with closings that have no verdict still imports; they show as not
    rated and stay out of the rate. Verdicts in a file are valid against the schema."""
    data = json.loads(SAMPLE.read_text())
    visit = next(v for v in data["visits"] if v["id"] == PCP)
    visit["closed_findings"] = [{"code": "C2", "amount": 80, "closed": "2026-10-01", "how": "marked dealt with"},
                                {"code": "C4", "amount": 80, "closed": "2026-10-01", "how": "marked wrong",
                                 "verdict": "wrong", "kind": "overpayment", "release": RELEASE}]
    path = tmp_path / "ingest.json"
    path.write_text(json.dumps(data))
    preview = web.import_preview(path)
    assert preview.status_code == 200 and "What will change" in preview.text, preview.text[:2000]
    token = preview.text.split('name="token" value="')[1].split('"')[0]
    assert web.client.post("/import/confirm", data={"token": token}, follow_redirects=False).status_code == 303
    page = text_of(web.client.get("/accuracy?year=2026").text)
    assert re.search(r"All findings 0 1 100\.0% 0", page) and "the 1 finding closed before the app asked" in page


# ---------- the owner's report ----------

@pytest.mark.postgres
def test_plt_02_2_owner_report_counts_only(household, app_db, pgdb, tmp_path, monkeypatch, capsys):
    """mhs-admin false-positives: over every household, counts only (no reasons, names, ids, dates of service or
    amounts); filtered by closing date, release and household."""
    from mhs.web.household import admin

    monkeypatch.setenv("MHS_DATABASE_URL", pgdb.url("app"))
    monkeypatch.setenv("MHS_KEY_FILE", str(tmp_path / "keys" / "app.kek"))
    monkeypatch.setenv("MHS_OBJECTS_DIR", str(household.objects_dir))
    homes = []
    for name, verdicts in (("First", ("wrong", "real")), ("Second", ("real", "real"))):
        hid = household.accounts.create_household(name)
        store = HouseholdStore(app_db, hid)
        store.upsert("provider", {"id": "prov-x", "name": "Secret Clinic"}, edited=True)
        for n, verdict in enumerate(verdicts):
            store.upsert("visit", {
                "id": f"v-2026-09-0{n + 1}-secret-clinic", "date": f"2026-09-0{n + 1}", "provider_id": "prov-x",
                "category": "provider_visit",
                "closed_findings": [closed("C2", verdict, "2026-10-10", "missed_adjustment", amount=4321)
                                    | {"reason": "Dr Secret said so"}]}, edited=True)
        homes.append(hid)

    admin.main(["false-positives"])
    out = capsys.readouterr().out
    assert "Households read: 2" in out
    assert re.search(r"Missed adjustment\s+3\s+1\s+25\.0%\s+0", out)
    assert "Overall: 1 wrong of 4 decided, 25.0%: ABOVE the target." in out
    assert f"Decided by release: {RELEASE} 4." in out
    for secret in ("Secret", "secret", "43.21", "4321", "2026-09-0", "prov-x", *homes, "First", "Second"):
        assert secret not in out, secret

    admin.main(["false-positives", "--household", homes[1], "--from", "2026-10-01", "--to", "2026-10-31",
                "--release", RELEASE])
    out = capsys.readouterr().out
    assert "Households read: 1" in out and "Overall: 0 wrong of 2 decided, 0.0%: meets the target." in out
    admin.main(["false-positives", "--from", "2026-10-11"])
    assert "Overall: 0 wrong of 0 decided, –: nothing decided yet." in capsys.readouterr().out
    with pytest.raises(SystemExit, match="Not a date"):
        admin.main(["false-positives", "--from", "October"])
    with pytest.raises(SystemExit, match="No such household"):
        admin.main(["false-positives", "--household", "00000000-0000-0000-0000-000000000000"])
