"""Scan an insurance card (ING-11, ADR-059): TC-ING-11-1 to 12 through the application tier, with a fake OCR engine that
reads the card's text, so the flow runs where Tesseract isn't installed."""

import re

import pytest

from mhs.data.household_store import HouseholdStore
from mhs.ingest.ocr import OcrResult
from mhs.web.household.features import Features
from tests import cards
from tests.conftest import admin_sql, csrf_from
from tests.pdfs import make_image
from tests.test_r1_admin import events, make_owner
from tests.test_r1_social import next_code

pytestmark = pytest.mark.postgres


class TextOcr:
    """Reads a synthetic card photo back as the text it was made from (the text is in the image's PNG comment)."""

    name = "fake"

    def __init__(self):
        self.texts: dict[bytes, str] = {}

    def photo(self, text: str) -> bytes:
        data = make_image(text)
        self.texts[data] = text
        return data

    def read(self, data: bytes, content_type: str) -> OcrResult:
        text = self.texts[data]
        return OcrResult(text, [], self.name, [text])


@pytest.fixture
def ocr(household):
    ocr = TextOcr()
    household.app.state.intake.ocr = ocr
    return ocr


def signed_in(household):
    who = household.enrol("Sample household")
    return who, household.sign_in(who)


def add_members(app_db, hid, *names):
    store = HouseholdStore(app_db, hid)
    for n in names:
        store.upsert("member", {"id": "mbr-" + n.split()[0].lower(), "name": n, "aliases": []}, edited=True)
    return store


def scan(client, ocr, front, back=None, plan=None):
    page = client.get("/coverage/card" + (f"?plan={plan}" if plan else "")).text
    files = {}
    if front is not None:
        files["front"] = ("front.png", ocr.photo(front), "image/png")
    if back is not None:
        files["back"] = ("back.png", ocr.photo(back), "image/png")
    return client.post("/coverage/card", data={"csrf_token": csrf_from(page), **({"plan": plan} if plan else {})},
                       files=files, follow_redirects=False)


def form_values(html: str) -> dict:
    """What a browser would post from the review form: inputs, textareas, checked boxes, selected options."""
    from html.parser import HTMLParser

    class P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.values, self.inside, self.select, self.area = {}, False, None, None

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag == "form":
                self.inside = "/confirm" in a.get("action", "")
            if not self.inside:
                return
            if tag == "input" and a.get("name"):
                if a.get("type") in ("checkbox", "radio"):
                    if "checked" in a:
                        self.values[a["name"]] = a.get("value", "on")
                else:
                    self.values[a["name"]] = a.get("value", "")
            elif tag == "select":
                self.select = a["name"]
                self.values.setdefault(self.select, "")
            elif tag == "option" and self.select and "selected" in a:
                self.values[self.select] = a.get("value", "")
            elif tag == "textarea":
                self.area = a["name"]
                self.values[self.area] = ""

        def handle_endtag(self, tag):
            if tag == "select":
                self.select = None
            if tag == "textarea":
                self.area = None
            if tag == "form":
                self.inside = False

        def handle_data(self, data):
            if self.area:
                self.values[self.area] += data

    p = P()
    p.feed(html)
    return p.values


def confirm(client, scan_url, **overrides):
    html = client.get(scan_url).text
    values = {**form_values(html), **overrides}
    return client.post(scan_url + "/confirm", data=values, follow_redirects=False), html


def card_rows(pgdb):
    """Row counts across every household (the app role, under row-level security, couldn't see them)."""
    [(scans, images)] = admin_sql(pgdb, "SELECT (SELECT count(*) FROM app.card_scans), "
                                        "(SELECT count(*) FROM app.card_images)")
    return {"scans": scans, "images": images}


def object_count(household):
    return sum(1 for p in household.objects_dir.rglob("*") if p.is_file())


def test_tc1_and_tc2_a_card_is_read_reviewed_and_confirmed(household, app_db, pgdb, ocr):
    who, c = signed_in(household)
    add_members(app_db, who.household_id, "Pat Sample", "Jordan Sample", "Alex Sample")
    r = scan(c, ocr, cards.EXAMPLE_FRONT, cards.EXAMPLE_BACK)
    assert r.status_code == 303 and r.headers["location"].startswith("/coverage/card/scn_")
    url = r.headers["location"]
    review = c.get(url).text
    # read: insurer, plan, type, group, member ID, people, date, copays, phone, address, each with a confidence or "check"
    for text in ("Example Health", "Choice Plus PPO", "0123456", "XJK123456789", "Pat Sample", "Jordan Sample",
                 "2026-01-01", "800-555-0100", "PO Box 1234, Springfield, IL 62701", "primary_care: 30.00",
                 "specialist: 60.00", "emergency: 350.00"):
        assert text in review, text
    assert "check" in review  # the insurer isn't a known name: a position guess, marked
    assert HouseholdStore(app_db, who.household_id).all("plan") == []  # nothing saved before Confirm
    # the scan holds tokens, never the printed identifiers
    with app_db.tx(who.household_id) as cx:
        stored = str(cx.execute("SELECT reading FROM app.card_scans").fetchone()["reading"])
    for private in ("XJK123456789", "0123456", "Pat Sample", "RX1234"):
        assert private not in stored
    r, _ = confirm(c, url)
    assert r.status_code == 303 and "/coverage?year=2026&saved=1" in r.headers["location"], r.text
    store = HouseholdStore(app_db, who.household_id)
    [plan] = store.all("plan")
    assert plan["insurer"] == "Example Health" and plan["plan_type"] == "PPO" and plan["plan_year"] == 2026
    assert plan["coverage_start"] == "2026-01-01"
    assert plan["copays"] == {"primary_care": 3000, "specialist": 6000, "urgent_care": 7500, "emergency": 35000}
    assert sorted(plan["member_ids"]) == ["mbr-alex", "mbr-jordan", "mbr-pat"]
    assert plan["member_numbers"]["mbr-pat"]["subscriber"] is True
    assert "terms_confirmed" not in plan or plan["terms_confirmed"] is False
    assert plan["group_number"].startswith("tok_") and "0123456" not in str(plan)
    assert "XJK123456789" not in str(plan) and plan["member_numbers"]["mbr-pat"]["member_number"].startswith("tok_")
    assert {c["label"] for c in plan["contacts"]} >= {"Member services", "Claims address", "Provider services"}
    assert "plan" in store.edited_ids("plan") or plan["id"] in store.edited_ids("plan")  # marked a member edit (ADR-011)
    page = c.get("/coverage?year=2026").text
    assert "0123456" in page and "XJK123456789" in page and 'href="tel:+18005550100"' in page
    assert card_rows(pgdb) == {"scans": 0, "images": 0}  # TC-10: nothing kept
    assert object_count(household) == 0


def test_tc3_the_same_card_again_changes_nothing_and_next_years_card_updates(household, app_db, pgdb, ocr):
    who, c = signed_in(household)
    add_members(app_db, who.household_id, "Pat Sample", "Jordan Sample", "Alex Sample")
    url = scan(c, ocr, cards.EXAMPLE_FRONT, cards.EXAMPLE_BACK).headers["location"]
    confirm(c, url)
    url = scan(c, ocr, cards.EXAMPLE_FRONT, cards.EXAMPLE_BACK).headers["location"]
    assert "Update" in c.get(url).text and "already on file" in c.get(url).text
    r, _ = confirm(c, url)
    assert "card=on_file" in r.headers["location"]
    store = HouseholdStore(app_db, who.household_id)
    assert len(store.all("plan")) == 1
    assert "already on file" in c.get("/coverage?year=2026&card=on_file").text
    nxt = scan(c, ocr, cards.EXAMPLE_FRONT_2027, cards.EXAMPLE_BACK).headers["location"]
    review = c.get(nxt).text
    assert "New plan year" in review and "Primary care copay: $30.00 to $35.00" in review
    confirm(c, nxt)
    assert sorted(p["plan_year"] for p in store.all("plan")) == [2026, 2027]


def test_a_scan_never_sets_terms_confirmed_and_clears_it_when_terms_change(household, app_db, pgdb, ocr):
    who, c = signed_in(household)
    add_members(app_db, who.household_id, "Pat Sample", "Jordan Sample", "Alex Sample")
    confirm(c, scan(c, ocr, cards.EXAMPLE_FRONT, cards.EXAMPLE_BACK).headers["location"])
    store = HouseholdStore(app_db, who.household_id)
    plan = store.all("plan")[0]
    store.upsert("plan", {**plan, "terms_confirmed": True}, edited=True)
    changed = cards.EXAMPLE_FRONT.replace("PCP $30", "PCP $45")
    confirm(c, scan(c, ocr, changed, cards.EXAMPLE_BACK).headers["location"])
    plan = store.get("plan", plan["id"])
    assert plan["copays"]["primary_care"] == 4500 and plan["terms_confirmed"] is False


def test_tc4_a_name_that_matches_nobody_needs_the_members_choice(household, app_db, pgdb, ocr):
    who, c = signed_in(household)
    add_members(app_db, who.household_id, "Pat Sample", "Jordan Sample")
    url = scan(c, ocr, cards.STRANGER_FRONT, cards.EXAMPLE_BACK).headers["location"]
    review = c.get(url).text
    assert "Add as a household member" in review and "Not in this household" in review and "Casey Stranger" in review
    r, _ = confirm(c, url)  # the choice for Casey and Alex is empty
    assert r.status_code == 400 and "Choose what to do with" in r.text
    store = HouseholdStore(app_db, who.household_id)
    assert store.all("plan") == [] and len(store.all("member")) == 2  # nothing done without the choice
    r, _ = confirm(c, url, person_2="add", person_1="none")  # Casey added, Jordan declined? (index 1 is Jordan)
    assert r.status_code == 303, r.text
    names = {m["name"] for m in store.all("member")}
    assert "Casey Stranger" in names


def test_tc6_front_only_saves_the_plan_and_offers_the_back(household, app_db, pgdb, ocr):
    who, c = signed_in(household)
    add_members(app_db, who.household_id, "Pat Sample", "Jordan Sample", "Alex Sample")
    confirm(c, scan(c, ocr, cards.EXAMPLE_FRONT).headers["location"])
    [plan] = HouseholdStore(app_db, who.household_id).all("plan")
    assert plan["card_back_missing"] is True and "contacts" not in plan
    page = c.get("/coverage?year=2026").text
    assert "Add the back of the card" in page
    r = scan(c, ocr, None, cards.EXAMPLE_BACK, plan=plan["id"])
    assert r.status_code == 303
    confirm(c, r.headers["location"])
    [plan] = HouseholdStore(app_db, who.household_id).all("plan")
    assert plan["card_back_missing"] is False and {x["label"] for x in plan["contacts"]} >= {"Member services"}
    assert "Add the back of the card" not in c.get("/coverage?year=2026").text


def test_tc7_a_dispute_letter_takes_the_member_id_from_the_card(household, app_db, pgdb, ocr):
    who, c = signed_in(household)
    store = add_members(app_db, who.household_id, "Pat Sample", "Jordan Sample", "Alex Sample")
    confirm(c, scan(c, ocr, cards.EXAMPLE_FRONT, cards.EXAMPLE_BACK).headers["location"])
    plan = store.all("plan")[0]
    host = household.app.state  # the PagesHost is reached through the pages; read the identifier the way letters do
    from mhs.web.household.app import HouseholdHost

    visit = type("V", (), {"bill_lines": [], "claims": [], "receipts": [],
                           "visit": {"plan_id": plan["id"], "member_id": "mbr-pat"}})()
    hh = HouseholdHost(host, app_db, household.app.state.intake.keyring, household.app.state.intake.objects, False,
                       household.app.state.intake.vault)
    assert hh.identifiers(None, store, visit)["member_number"] == "XJK123456789"


def test_tc8_a_non_card_and_a_blurry_photo_are_refused_plainly(household, pgdb, ocr):
    who, c = signed_in(household)
    r = scan(c, ocr, cards.NOT_A_CARD)
    assert r.status_code == 400 and "look like an insurance card" in r.text
    r = scan(c, ocr, " ")  # a blank photo
    assert r.status_code == 400 and "couldn&#39;t read any text" in r.text


def test_tc12_dental_makes_a_separate_plan_and_vision_is_not_read(household, app_db, pgdb, ocr):
    who, c = signed_in(household)
    store = add_members(app_db, who.household_id, "Pat Sample", "Jordan Sample", "Alex Sample")
    confirm(c, scan(c, ocr, cards.EXAMPLE_FRONT, cards.EXAMPLE_BACK).headers["location"])
    medical = store.all("plan")[0]
    url = scan(c, ocr, cards.DENTAL_FRONT, cards.DENTAL_BACK).headers["location"]
    assert "New plan" in c.get(url).text and "separate dental plan" in c.get(url).text
    confirm(c, url, person_0="mbr-pat")
    plans = {p["id"]: p for p in store.all("plan")}
    assert len(plans) == 2 and plans[medical["id"]] == medical  # the medical plan is unchanged
    dental = next(p for p in plans.values() if p.get("coverage_kind") == "dental")
    assert dental["insurer"] == "Sample Dental Plan" or "Dental" in dental["insurer"]
    assert "Dental" in c.get("/coverage?year=2026").text
    r = scan(c, ocr, cards.VISION_FRONT, cards.VISION_BACK)
    assert r.status_code == 400 and "Type a vision plan in on Coverage" in r.text
    assert len(store.all("plan")) == 2


def test_tc10_abandoning_and_a_scan_left_open_leave_no_image(household, app_db, pgdb, ocr):
    who, c = signed_in(household)
    url = scan(c, ocr, cards.EXAMPLE_FRONT, cards.EXAMPLE_BACK).headers["location"]
    assert card_rows(pgdb) == {"scans": 1, "images": 2} and object_count(household) == 2
    assert c.get(url + "/front").headers["content-type"] == "image/jpeg"
    page = c.get(url).text
    assert c.post(url + "/cancel", data={"csrf_token": csrf_from(page)}, follow_redirects=False).status_code == 303
    assert card_rows(pgdb) == {"scans": 0, "images": 0} and object_count(household) == 0
    scan(c, ocr, cards.EXAMPLE_FRONT, cards.EXAMPLE_BACK)  # left open
    assert object_count(household) == 2
    cards_store = household.app.state.card_store
    assert cards_store.expire() == 0  # a fresh scan stays
    admin_sql(pgdb, "UPDATE app.card_scans SET created_at = now() - interval '25 hours'")
    assert cards_store.expire() == 2
    assert card_rows(pgdb) == {"scans": 0, "images": 0} and object_count(household) == 0


def test_tc11_keeping_images_is_an_owner_setting_and_they_are_exported_and_deleted(household, app_db, pgdb, ocr):
    import io
    import zipfile

    who, c = signed_in(household)
    other = household.enrol("Other household")
    owner = household.enrol("Owner household")
    make_owner(household, owner)
    o = household.sign_in(owner)
    # a member who isn't an owner can't reach the setting
    assert c.get("/admin").status_code == 404
    assert c.post("/admin/keep-card-images", data={"state": "on", "csrf_token": household.csrf(c)}).status_code == 404
    page = o.get("/admin").text
    assert "Not kept" in page and "In review now" in page
    assert o.post("/admin/keep-card-images", data={"state": "on", "csrf_token": csrf_from(page)},
                  follow_redirects=False).status_code == 303
    assert Features(app_db).keep_card_images() and "setting_keep_card_images_on" in events(app_db, prefix="setting_")
    add_members(app_db, who.household_id, "Pat Sample", "Jordan Sample", "Alex Sample")
    confirm(c, scan(c, ocr, cards.EXAMPLE_FRONT, cards.EXAMPLE_BACK).headers["location"])
    store = HouseholdStore(app_db, who.household_id)
    [plan] = store.all("plan")
    assert len(plan["card_documents"]) == 2 and card_rows(pgdb) == {"scans": 0, "images": 2}
    assert object_count(household) == 2
    for img in c.get("/coverage?year=2026").text.split('href="/coverage/card-image/')[1:]:
        assert c.get("/coverage/card-image/" + img.split('"')[0]).status_code == 200
    # the other household can't see them
    img_id = plan["card_documents"][0]
    assert household.sign_in(other).get(f"/coverage/card-image/{img_id}").status_code == 404
    admin_page = o.get("/admin").text
    assert "Kept: <strong>2</strong>" in admin_page and "Delete kept card images" in admin_page
    # exported with the household's data
    export = c.post("/data/export", data={"password": who.password, "csrf_token": household.csrf(c)})
    names = zipfile.ZipFile(io.BytesIO(export.content)).namelist()
    assert len([n for n in names if n.startswith("files/cards/")]) == 2
    # turning it off keeps what is kept; the owner can delete them
    o.post("/admin/keep-card-images", data={"state": "off", "csrf_token": csrf_from(admin_page)})
    assert card_rows(pgdb)["images"] == 2
    o.post("/admin/delete-kept-card-images", data={"csrf_token": csrf_from(o.get("/admin").text)})
    assert card_rows(pgdb) == {"scans": 0, "images": 0} and object_count(household) == 0
    assert "Card front" not in c.get("/coverage?year=2026").text


def test_kept_images_go_with_a_deleted_household(household, app_db, pgdb, ocr):
    who, c = signed_in(household)
    Features(app_db).set("keep_card_images", True)
    add_members(app_db, who.household_id, "Pat Sample", "Jordan Sample", "Alex Sample")
    confirm(c, scan(c, ocr, cards.EXAMPLE_FRONT, cards.EXAMPLE_BACK).headers["location"])
    assert object_count(household) == 2
    r = c.post("/data/delete", data={"password": who.password, "code": next_code(household, who), "confirm": "DELETE",
                                     "csrf_token": household.csrf(c)})
    assert r.status_code == 200
    assert object_count(household) == 0


def test_consent_gates_the_scan(household, app_db, pgdb, ocr):
    who, c = signed_in(household)
    Features(app_db).set("require_consent", True)
    r = scan(c, ocr, cards.EXAMPLE_FRONT, cards.EXAMPLE_BACK)
    assert r.status_code == 400 and "without your consent" in r.text
    assert card_rows(pgdb) == {"scans": 0, "images": 0}


def test_a_scan_belongs_to_its_member(household, app_db, pgdb, ocr):
    who, c = signed_in(household)
    url = scan(c, ocr, cards.EXAMPLE_FRONT, cards.EXAMPLE_BACK).headers["location"]
    other = household.sign_in(household.enrol("Another"))
    assert other.get(url).status_code == 404 and other.get(url + "/front").status_code == 404
    assert household.client().get(url, follow_redirects=False).headers["location"] == "/signin"
