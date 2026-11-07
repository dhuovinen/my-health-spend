"""Provider charges over time (UX-11): the page's chart, table, filters and switch, on both apps."""

import copy
import re

from mhs.core import charges
from tests.test_r1_reconcile_pages import SETTINGS, eob, import_data, text_of
from tests.test_web import web  # noqa: F401 (fixture)

YEAR = 2026


def data():
    """Two providers and three members in 2026, two bills in 2025 and one in 2024."""
    d = {"schema_version": "0.1", **copy.deepcopy(SETTINGS)}
    d["members"] = [{"id": "me", "name": "Pat Example"}, {"id": "kid", "name": "Sam Example"}, {"id": "sib", "name": "Lee Example"}]
    d["providers"] = [{"id": "prov-a", "name": "Alpha Clinic", "kind": "physician_practice"},
                      {"id": "prov-b", "name": "Beta Labs", "kind": "physician_practice"}]
    d["plans"] += [{**d["plans"][0], "id": f"plan-{y}", "plan_year": y} for y in (2024, 2025)]

    def v(vid, day, provider="prov-a", member="me", plan="plan"):
        return {"id": vid, "date": day, "provider_id": provider, "member_id": member, "plan_id": plan,
                "category": "provider_visit"}

    def claim(vid, day, provider="prov-a", plan="plan", billed=400, owed=80, lines=None):
        return {"id": f"eob-{vid}", "type": "eob", "date": day, "plan_id": plan, "provider_id": provider, "visit_id": vid,
                "claim_number": f"C-{vid}", "claim_status": "processed", "billed": billed, "allowed": owed,
                "adjustment": billed - owed, "insurer_paid": 0, "deductible": owed, "copay": 0, "coinsurance": 0,
                "not_covered": 0, "patient_responsibility": owed, **({"lines": lines} if lines else {})}

    lines = [{"code": "99213", "description": "Visit", "billed": 200, "allowed": 50, "adjustment": 150, "insurer_paid": 0, "patient_responsibility": 50},
             {"code": "80061", "description": "Lab", "billed": 100, "allowed": 20, "adjustment": 80, "insurer_paid": 0, "patient_responsibility": 20},
             {"code": "36415", "description": "Draw", "billed": 100, "allowed": 10, "adjustment": 90, "insurer_paid": 0, "patient_responsibility": 10}]
    d["visits"] = [v("a1", "2026-02-10"), v("a2", "2026-02-10", member="kid"), v("a3", "2026-05-05", "prov-b", "sib"),
                   v("old1", "2025-03-01", plan="plan-2025"), v("old2", "2025-09-01", plan="plan-2025"),
                   v("older", "2024-03-01", plan="plan-2024"), v("nobill", "2026-07-01", "prov-b"),
                   v("noeob", "2026-08-01", "prov-b")]
    d["documents"] = [claim("a1", "2026-02-20", lines=lines), claim("a2", "2026-02-20", owed=50),
                      claim("a3", "2026-05-20", "prov-b"), claim("old1", "2025-03-20", plan="plan-2025"),
                      claim("old2", "2025-09-20", plan="plan-2025"), claim("older", "2024-03-20", plan="plan-2024"),
                      {"id": "pay-1", "type": "payment", "date": "2026-07-02", "provider_id": "prov-b", "account_id": "hsa",
                       "amount": 10, "allocations": [{"visit_id": "nobill", "amount": 10}]},
                      {"id": "s-1", "type": "provider_bill", "date": "2026-08-10", "provider_id": "prov-b", "balance_due": 300,
                       "lines": [{"visit_id": "noeob", "billed_charge": 300, "patient_amount": 300}]}]
    return d


def page(web, query=""):
    return web.client.get(f"/charges?year={YEAR}&member={query}").text


def dots(html):
    return re.findall(r'<a class="dot" href="#bill-([^"]+)"', html)


def rows(html):
    return re.findall(r'<details class="bill" id="bill-([^"]+)"', html)


def test_tc_ux_11_1_2_one_dot_per_bill_with_a_member_color_and_legend(web, tmp_path):
    import_data(web, tmp_path, data())
    html = page(web)
    assert set(dots(html)) == {"a1", "a2", "a3", "noeob"}
    assert set(rows(html)) == {"a1", "a2", "a3", "noeob", "nobill"}
    for name in ("Pat Example", "Sam Example", "Lee Example"):
        assert name in text_of(html.split('class="legend')[1])
    colors = dict(re.findall(r'href="#bill-([^"]+)".*?class="mark (mc-\S+?)"', html, re.S))
    assert colors["a1"] == colors["noeob"] != colors["a2"] != colors["a3"]  # one color per member, across providers
    assert 'data-provider="Alpha Clinic"' in html and 'data-member="Sam Example"' in html and 'data-billed="$400.00"' in html
    assert 'data-share="$50.00"' in html and "data-status=" in html  # what a hover, focus or tap shows


def test_tc_ux_11_4_5_6_the_prior_year(web, tmp_path):
    import_data(web, tmp_path, data())
    html = page(web)
    assert "2 earlier bills in 2025" in text_of(html) and "old1" not in dots(html)
    both = web.client.get(f"/charges?year={YEAR}&member=&prior=1").text
    assert {"old1", "old2"} < set(dots(both)) and "older" not in rows(both)  # never two years back
    assert 'class="year-line"' in both and "Show 2026 only" in text_of(both)
    beta = page(web, "&provider=" + re.search(r'<option value="([^"]+)"[^>]*>Beta Labs', html).group(1))
    assert "earlier bill" not in text_of(beta) and "Include 2025" not in beta


def test_tc_ux_11_7_8_filters_are_in_the_url_and_can_match_nothing(web, tmp_path):
    import_data(web, tmp_path, data())
    assert set(rows(page(web, "kid"))) == {"a2"}
    group = re.search(r'<option value="([^"]+)"[^>]*>Alpha Clinic', page(web)).group(1)
    assert set(rows(page(web, f"me&provider={group}"))) == {"a1"}
    none = page(web, f"sib&provider={group}")
    assert rows(none) == [] and dots(none) == [] and "No bills match" in text_of(none) and "Clear the filters" in text_of(none)
    assert f'value="{group}" selected' in none  # restored after a reload


def test_tc_ux_11_9_10_line_items_and_totals_only(web, tmp_path):
    import_data(web, tmp_path, data())
    html = page(web)
    a1 = html.split('id="bill-a1"')[1].split("</details>")[0]
    assert "99213" in a1 and "80061" in a1 and "$200.00" in a1 and "add up" not in a1
    assert "shows totals only" in html.split('id="bill-a2"')[1].split("</details>")[0]


def test_tc_ux_11_11_14_15_the_amount_switch_and_what_has_no_amount(web, tmp_path):
    import_data(web, tmp_path, data())
    billed = page(web)
    assert "nobill" not in dots(billed) and "1 bill with no billed amount" in text_of(billed)
    share = web.client.get(f"/charges?year={YEAR}&member=&view=share").text
    assert 'value="share" selected' in share
    assert "noeob" not in dots(share) and "noeob" in rows(share) and "with no member's share yet" in text_of(share)
    y = dict(re.findall(r'href="#bill-([^"]+)".*?class="hit" cx="[^"]+" cy="([^"]+)"', billed, re.S))
    assert y["a1"] == y["a2"]  # level on billed
    y = dict(re.findall(r'href="#bill-([^"]+)".*?class="hit" cx="[^"]+" cy="([^"]+)"', share, re.S))
    assert y["a1"] != y["a2"]  # they differ on the member's share


def test_tc_ux_11_12_the_same_spot_keeps_both_dots_reachable():
    b = [charges.Bill("x", "P", "g", "me", "Me", "2026-02-01", 100, 10, "Complete"),
         charges.Bill("y", "P", "g", "kid", "Kid", "2026-02-01", 100, 10, "Complete")]
    a, c = charges.chart(b, "billed", 2026, 2026, {"me": 0, "kid": 1}).dots
    assert a.y == c.y and abs(a.x - c.x) == charges.OVERLAP


def test_tc_ux_11_13_no_inline_styles_scripts_or_third_parties(web, tmp_path):
    import_data(web, tmp_path, data())
    html = page(web)
    assert 'style="' not in html and "<script>" not in html and "onclick" not in html
    assert not re.search(r'(src|href)="https?://', html)
