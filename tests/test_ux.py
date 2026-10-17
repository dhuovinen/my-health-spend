"""Phase 1.5 web experience (UX-01, UX-02, UX-06; ADR-041), on both apps, with the synthetic three-person household
in samples/household-ingest.json (tools/make_household_sample.py). Layout at 375px and 1280px (UX-10) is in
tests/test_ux_layout.py."""

import json
import re
from datetime import date

import pytest

from mhs.config import ROOT
from mhs.core import edits
from mhs.core.household import NOBODY, household_totals, visits_for
from mhs.core.reconcile import ATTENTION, Dataset, build_report
from mhs.data.importer import commit, prepare
from mhs.data.repository import load_dataset
from mhs.data.store import Store
from mhs.web.pages import attention_queue, case_history, line_rows
from tests.test_web import web  # noqa: F401  (the fixture: both apps)

HOUSEHOLD = ROOT / "samples" / "household-ingest.json"
PEDS = "v-2026-08-11-peds"  # Sam's six-line visit; the statement skips the discount on 96110
TODAY = date(2026, 10, 17)


def import_household(web):
    preview = web.import_preview(HOUSEHOLD)
    assert preview.status_code == 200 and "What will change" in preview.text, preview.text[:2000]
    token = preview.text.split('name="token" value="')[1].split('"')[0]
    assert web.client.post("/import/confirm", data={"token": token}, follow_redirects=False).status_code == 303


@pytest.fixture
def report(tmp_path):
    store = Store(tmp_path / "mhs.db")
    plan = prepare(json.loads(HOUSEHOLD.read_text()), store, str(HOUSEHOLD), HOUSEHOLD.parent)
    assert plan.ok, plan.errors
    commit(plan, store, tmp_path / "documents")
    return store, build_report(load_dataset(store), 2026, TODAY)


def card(html: str, visit_id: str) -> str:
    """The visit card for one visit in a page."""
    m = re.search(rf'<a class="card visit-card[^"]*" href="/visits/{visit_id}">(.*?)</a>\s*(?=<a class="card visit-card|</div>)',
                  html, re.S)
    assert m, f"no card for {visit_id}"
    return m.group(1)


# ---------- UX-01 home ----------

def test_tc_ux_01_1_home_order_and_cards(web):
    """Summary tiles, then the attention queue, then visit cards with person, provider, date, status badge,
    document completeness and amount at issue (ADR-023)."""
    import_household(web)
    home = web.client.get("/").text
    order = [home.index(f'id="{part}"') for part in ("summary", "attention", "visits", "hsa")]
    assert order == sorted(order)
    assert home.index('class="grid tiles"') < home.index('id="attention"')
    peds = card(home, PEDS)
    for text in ("Example Pediatrics", "Aug 11, 2026", "Sam Sample", "Discrepancy found", "3 of 4 documents",
                 "At issue", "$15.00"):
        assert text in peds, text
    assert "No one assigned" in card(home, "v-2026-06-15-vitamins")
    # the attention queue explains each item in plain words and says how it is ranked (UX-04, UX-05)
    queue = home[home.index('id="attention"'):home.index('id="visits"')]
    assert "Most dollars first" in queue and "Missed adjustment:" in queue and "$15.00" in queue
    assert queue.index("Example Imaging Center") < queue.index("Example Pediatrics")  # $900 owed before $433


def test_tc_ux_01_2_empty_home_links_to_uploads_on_release_1(web):
    page = web.client.get("/").text
    assert "No visits yet" in page and 'href="/import"' in page
    if "Sign out" in page:  # Release 1: uploads are the way in
        assert 'href="/uploads"' in page and "Upload your first documents" in page


def test_tc_ux_01_3_card_amount_at_issue_is_the_open_findings(report):
    """The card's amount at issue is the visit's open money findings, the same dollars counted once (ADR-035, 041)."""
    store, rep = report
    def money(v):  # open findings about money; a balance owed (C6) and an unfiled claim are shown beside it
        return [f.amount for f in v.findings if f.code not in ("C6", "claim_filed")]

    peds = rep.visit(PEDS)
    assert money(peds) == [1500] and peds.at_stake == 1500
    # the bill's $80 excess was also paid: one finding on the bill, one on the payment, $80 at issue, not $160
    pcp = rep.visit("v-2026-04-02-pcp")
    assert sorted(money(pcp)) == [8000, 8000] and pcp.at_stake == 8000
    for v in rep.visits:
        assert v.at_stake == max(money(v), default=0), v.id
    # closing the finding takes it off the card
    visit = store.get("visit", PEDS)
    store.upsert("visit", edits.close_finding(visit, "C2", 1500, "2026-10-17"), edited=True)
    assert build_report(load_dataset(store), 2026, TODAY).visit(PEDS).at_stake == 0


def test_card_amount_on_the_page_and_after_closing(web):
    import_household(web)
    assert "$15.00" in card(web.client.get("/").text, PEDS)
    web.client.post(f"/visits/{PEDS}/findings", data={"code": "C2", "amount": "1500"})
    peds = card(web.client.get("/").text, PEDS)
    assert "$15.00" not in peds and ">None<" in peds and "Balance outstanding" in peds  # $418.00 is still owed


def test_attention_queue_ranks_by_dollars_then_age():
    def v(vid, day, status, stake, owed):
        class V:
            pass
        x = V()
        x.id, x.visit, x.status, x.at_stake, x.remaining = vid, {"date": day}, status, stake, owed
        return x

    visits = [v("a", "2026-03-01", "discrepancy", 1500, 0), v("b", "2026-02-01", "balance_outstanding", 0, 8000),
              v("c", "2026-01-01", "needs_review", 0, 1500), v("d", "2026-01-05", "complete", 0, 0)]
    assert [x.id for x in attention_queue(visits)] == ["b", "c", "a"]  # $80; then $15 twice, the older first


# ---------- UX-02 visit detail ----------

def test_tc_ux_02_1_visit_detail_has_everything_on_one_page(web):
    """Documents, line comparison, allocation, findings and case history on one page, in the order of ADR-041."""
    import_household(web)
    web.client.post(f"/visits/{PEDS}/dispute", data={"action": "open", "note": "Called billing about 96110"})
    web.client.post("/notes", data={"provider_id": "prov-peds", "visit_id": PEDS, "date": "2026-10-16",
                                    "channel": "phone", "direction": "sent", "text": "Asked for a corrected bill"})
    web.client.post(f"/visits/{PEDS}/expected", data={"kind": "itemized_bill", "state": "not_applicable"})
    page = web.client.get(f"/visits/{PEDS}").text
    sections = [page.index(f'id="{s}"') for s in ("findings", "allocation", "lines", "documents", "history")]
    assert sections == sorted(sections)
    for jump in ("#findings", "#lines", "#allocation", "#documents", "#history"):
        assert f'href="{jump}"' in page
    history = page[page.index('id="history"'):page.index('id="notes"')]
    for text in ("You opened a dispute", "Called billing about 96110", "Note (Phone · Sent)", "Asked for a corrected bill",
                 "Itemized bill: not needed", "Provider statement", "Insurance decision (EOB)",
                 "The insurer received the claim", "Well-child visit and vaccines"):
        assert text in history, text
    assert history.index("Note (Phone") < history.index("Provider statement") < history.index("Insurance decision")
    assert "In dispute" in page and "Where the billed amount went" in page and "Payments applied" in page


def test_tc_ux_02_2_lines_that_disagree_show_the_difference(web):
    import_household(web)
    page = web.client.get(f"/visits/{PEDS}").text
    table = page[page.index('class="small line-compare"'):page.index("</table>", page.index("line-compare"))]
    rows = re.findall(r"<tr class=\"([^\"]*)\">(.*?)</tr>", table, re.S)
    assert len(rows) == 6
    disagree = [body for cls, body in rows if cls == "disagree"]
    assert len(disagree) == 1 and "96110" in disagree[0] and "+$15.00 asked" in disagree[0]
    assert sum("Agrees" in body for cls, body in rows if cls != "disagree") == 5


def test_line_rows_and_case_history_units(report):
    store, rep = report
    peds = rep.visit(PEDS)
    rows = line_rows(peds.line_match)
    [bad] = [r for r in rows if r["disagree"]]
    assert bad["you_diff"] == 1500 and bad["charge_diff"] == 0 and bad["asked"] == 3500 and bad["owed"] == 2000
    assert line_rows(None) == []
    history = case_history(peds, [], {})
    assert [h["date"] for h in history] == sorted((h["date"] for h in history), reverse=True)
    assert history[-1] == {"date": "2026-08-11", "what": "Visit", "detail": "Well-child visit and vaccines"}


# ---------- UX-06 household ----------

def test_tc_ux_06_1_person_totals_sum_to_the_family(report):
    store, rep = report
    people, family = household_totals(rep.visits, store.all("member"), ATTENTION)
    assert [(p.name, p.visits) for p in people] == [("Alex Sample", 2), ("Jordan Sample", 3), ("Sam Sample", 1),
                                                    ("Not assigned to anyone", 1)]
    assert people[-1].member_id == NOBODY
    for field in ("visits", "billed", "insurer_paid", "paid", "still_owed", "at_issue", "attention"):
        assert sum(getattr(p, field) for p in people) == getattr(family, field), field
    assert family.billed == sum(v.total_billed for v in rep.visits)
    assert family.at_issue == sum(v.at_stake for v in rep.visits) == 9500
    assert sum(family.status_counts.values()) == len(rep.visits) == 7
    sam = next(p for p in people if p.member_id == "mem-sam")
    assert (sam.billed, sam.still_owed, sam.at_issue) == (59500, 41800, 1500)
    assert visits_for(rep.visits, "mem-sam") == [rep.visit(PEDS)] and visits_for(rep.visits, None) == rep.visits


def test_a_removed_members_visits_count_as_unassigned(web):
    import_household(web)
    web.store.delete("member", "mem-sam", edited=True)
    page = web.client.get("/household").text
    assert "Sam Sample" not in page.split('id="people"')[1].split("</table>")[0]
    unassigned = web.client.get("/visits?year=2026&member=none").text
    assert "2 of 7" in unassigned and PEDS in unassigned


def test_household_totals_without_members():
    rep = build_report(Dataset(), 2026, TODAY)
    people, family = household_totals(rep.visits, [], ATTENTION)
    assert people == [] and family.visits == 0 and family.billed == 0


def test_household_page_lists_people_and_family(web):
    import_household(web)
    page = web.client.get("/household").text
    for text in ("Jordan Sample", "Alex Sample", "Sam Sample", "Not assigned to anyone", "Family"):
        assert text in page
    assert 'href="/visits?year=2026&amp;member=none"' in page
    unassigned = web.client.get("/visits?year=2026&member=none").text
    assert "1 of 7" in unassigned and "Example Vitamin Shop" in unassigned
    assert "Sam Sample in-network deductible" in page  # each person's own limits


def test_tc_ux_06_2_switch_individual_and_family_kept_across_pages(web):
    import_household(web)
    r = web.client.post("/view", data={"member": "mem-sam", "next": "/household"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/household"
    assert "httponly" in r.headers["set-cookie"].lower() and "samesite=lax" in r.headers["set-cookie"].lower()
    home = web.client.get("/").text
    assert "Showing <strong>Sam Sample</strong>" in home
    assert re.findall(r'class="card visit-card[^"]*" href="/visits/([^"]+)"', home) == [PEDS]
    assert "$595.00" in home[home.index('id="summary"'):home.index('id="attention"')]  # Sam's billed only
    assert "Jordan Sample in-network deductible" not in home and "Sam Sample in-network deductible" in home
    visits = web.client.get("/visits?year=2026").text
    assert "1 of 7" in visits and re.findall(r'class="card visit-card[^"]*" href="/visits/([^"]+)"', visits) == [PEDS]
    assert "7 of 7" in web.client.get("/visits?year=2026&member=").text  # "All" in the filter still means all
    assert '<span class="chip info">showing</span>' in web.client.get("/household").text
    # back to the family
    web.client.post("/view", data={"member": "", "next": "/"})
    home = web.client.get("/").text
    assert "Showing <strong>" not in home and len(re.findall(r'class="card visit-card', home)) == 7
    # an unknown member falls back to the family
    web.client.post("/view", data={"member": "mem-nobody"})
    assert "7 of 7" in web.client.get("/visits?year=2026").text


@pytest.mark.postgres
def test_view_switch_needs_the_csrf_token_and_ends_at_sign_out(household):
    from tests.test_web import ReleaseOne

    member = ReleaseOne(household, None)
    raw = member.client.client
    assert raw.post("/view", data={"member": ""}, follow_redirects=False).status_code == 403
    r = member.client.post("/view", data={"member": ""}, follow_redirects=False)
    assert r.status_code == 303
    raw.cookies.set("mhs_view", "mem-sam")
    r = member.client.post("/signout", follow_redirects=False)
    assert 'mhs_view=""' in r.headers.get("set-cookie", "") or "mhs_view=;" in r.headers.get("set-cookie", "")
