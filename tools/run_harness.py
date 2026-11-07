"""Run the made-up test data in samples/harness through the real app, end to end, and report what it concluded.

    uv run tools/run_harness.py                    # start the stack, ingest everything, write harness-output/
    uv run tools/run_harness.py login <email>      # a harness member's password and current 6-digit code

The CSV is the source of truth and the PDFs are generated from it (tools/make_harness_pdfs.py). Each family runs
three ways, in separate households: from the CSV, converted to the claims and HSA export layouts the app accepts;
from its PDFs, uploaded one by one; and from its invoices and exports together. Every step goes through the app's own pages: sign in, upload, wait for the
worker, confirm what it extracted without a person checking it. The results are compared with the CSV's answers.

Synthetic data only. The work runs inside the compose `tests` container (`--inside`), which has Chromium and reaches
the stack's database, as tools/perf_run.py does. Exit code 0 means the run finished, even with mismatches; --strict
makes a mismatch fail too.
"""

import argparse
import csv
import html
import io
import json
import os
import re
import secrets
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT)]
INPUT = "samples/harness"
OUTPUT = "harness-output"
YEAR = 2026
WAIT_SECONDS = 180
PAGES = [("home", "/"), ("visits", f"/visits?year={YEAR}"), ("household", "/household"), ("providers", "/providers"),
         ("tax", f"/tax?year={YEAR}"), ("cases", "/cases"), ("accuracy", "/accuracy"), ("uploads", "/uploads")]
MAX_VISIT_SHOTS = 6
DATA_NOTES = [
    "St. Jude's second CSV row (EOB-HEN-2003, $0.00 billed) repeats $556.00 already inside the first row's $2,576.00. "
    "The harness treats it as a payment, not a new charge; taken literally the visit would owe $3,132.00.",
    "Maya Truman's 2026-11-04 visit has an EOB dated 2026-11-18 and an HSA payment dated 2026-11-28, which can be "
    "later than the day this runs.",
    "For the PDF households, each invoice should make one visit with the amount due it prints. The app has no way to "
    "read HSA payments from a PDF statement or claims from a family-wide EOB, so payments and statuses aren't expected.",
]

# What each of the CSV's statuses should look like in the app's nine visit statuses. This mapping is the harness's
# reading of the CSV's words; a visit takes the first of these its rows contain.
EXPECTED_STATUS = [
    ("Timing", {"needs_review", "discrepancy", "awaiting_eob"}),
    ("Unreconciled", {"balance_outstanding", "discrepancy"}),
    ("Partially", {"complete", "resolved"}),  # both tranches are in the data, so nothing is left owing
    ("Fully", {"complete", "resolved"}),
    ("Matched", {"complete", "resolved"}),
]
RELATIONSHIP = {"primary subscriber": "self", "spouse": "spouse", "dependent child": "child"}
# Not in the CSV: the Truman EOB prints the $6,400 family deductible, a Henderson note gives David's $4,000.
PLANS = {"The Trumans": ("family", 640000), "The Hendersons": ("individual", 400000)}


# ---------- the CSV: pure functions, tested without a stack (tests/test_harness.py) ----------

def read_master(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))


def cents(value: str) -> int:
    return round(float(value or 0) * 100)


def is_tranche(r: dict) -> bool:
    """A later payment on a charge already counted: St. Jude's second row bills and allows $0.00 but repeats $556.00
    of the first row's $2,576.00. It carries an HSA payment and no charge of its own."""
    return not cents(r["Billed_Charge"]) and not cents(r["Negotiated_Allowed_Amount"])


def members_of(rows: list[dict]) -> list[dict]:
    seen = {}
    for r in rows:
        seen.setdefault(r["Member_Name"], RELATIONSHIP.get(r["Member_Relationship"].lower(), "other"))
    return [{"name": name, "relationship": rel} for name, rel in seen.items()]


def claims_csv(rows: list[dict]) -> str:
    """One row per claim per provider, in a layout the app accepts as an insurer's claims export. The master has a
    row per service code, and sometimes two providers on one claim number, which would overwrite each other."""
    grouped = defaultdict(list)
    for r in rows:
        if not is_tranche(r):
            grouped[(r["EOB_Claim_Number"], r["Provider_Name"], r["Date_of_Service"], r["Member_Name"])].append(r)
    used = defaultdict(int)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Provider", "Claim Number", "Patient", "Service Date", "Processed Date", "Status", "Billed", "Allowed",
                "Plan Paid", "Deductible", "Copay", "Coinsurance", "You Owe"])
    for (claim, provider, when, member), group in grouped.items():
        used[claim] += 1
        number = claim if used[claim] == 1 else f"{claim}-{used[claim]}"
        total = lambda k: f"{sum(cents(r[k]) for r in group) / 100:.2f}"  # noqa: E731
        w.writerow([provider, number, member, when, group[0]["EOB_Adjudication_Date"], "Processed",
                    total("Billed_Charge"), total("Negotiated_Allowed_Amount"), total("Insurance_Paid_Amount"),
                    total("Member_Deductible"), total("Member_Copay"), total("Member_Coinsurance"),
                    total("Total_Member_Responsibility")])
    return out.getvalue()


def hsa_csv(rows: list[dict]) -> str:
    """One row per HSA payment (a transaction can cover several service codes), in the HSA export layout."""
    paid = defaultdict(int)
    for r in rows:
        if r["HSA_Transaction_ID"] and cents(r["HSA_Amount_Paid"]):
            paid[(r["HSA_Payment_Date"], r["HSA_Transaction_ID"], r["Provider_Name"])] += cents(r["HSA_Amount_Paid"])
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Date", "Description", "Amount"])
    for (when, _txn, provider), amount in sorted(paid.items()):
        w.writerow([when, f"Payment to {provider.replace(',', '')}", f"-{amount / 100:.2f}"])
    return out.getvalue()


def expected_visits(rows: list[dict]) -> list[dict]:
    """The master's answer per visit: one visit is a person, a provider and a date."""
    grouped = defaultdict(list)
    for r in rows:
        grouped[(r["Date_of_Service"], r["Provider_Name"], r["Member_Name"])].append(r)
    visits = []
    for (when, provider, member), group in sorted(grouped.items()):
        words = " ".join(r["Reconciliation_Match_Status"] for r in group)
        label, accept = next((k, v) for k, v in EXPECTED_STATUS if k in words)
        visits.append({"date": when, "provider": provider, "member": member,
                       "owed": sum(cents(r["Total_Member_Responsibility"]) for r in group if not is_tranche(r)),
                       "paid": sum(cents(r["HSA_Amount_Paid"]) for r in group),
                       "expected": next(r["Reconciliation_Match_Status"] for r in group if label in
                                        r["Reconciliation_Match_Status"]),
                       "accept": sorted(accept)})
    return visits


def expected_from_invoices(rows: list[dict], pages: dict[str, list[str]]) -> list[dict]:
    """What the PDFs alone can show, one visit per invoice: the amount due it prints. An invoice can name a practitioner
    and a facility, and the app may file the visit under either. Payments and statuses can't be expected (DATA_NOTES)."""
    invoices = defaultdict(list)
    for r in rows:
        invoices[r["Provider_Invoice_Asset_PDF"]].append(r)
    visits = []
    for name, group in invoices.items():
        due = re.search(r"Amount due: \$([\d,.]+)", pages[name][-1]).group(1).replace(",", "")
        first = group[0]
        visits.append({"date": first["Date_of_Service"], "provider": first["Provider_Name"], "member": first["Member_Name"],
                       "match": [r["Provider_Name"] for r in group] + [first["Facility_Name"]], "owed": cents(due),
                       "paid": None, "accept": None, "expected": "Amount due on the invoice"})
    return sorted(visits, key=lambda v: (v["date"], v["provider"]))


def expected_type(name: str) -> str:
    if name.startswith("eob_"):
        return "eob"
    return "hsa_statement" if name.startswith("hsa_") else "provider_statement|itemized_bill"


def compare(expected: list[dict], actual: list[dict]) -> tuple[list[dict], list[dict]]:
    """(one row per expected visit, the app's visits nobody expected). A visit matches on its date and on the
    provider's name, or any of the expected entry's `match` names; a person, when both sides name one, must agree."""
    plain = lambda name: name.replace("\u2019", "'").lower()  # noqa: E731
    left = list(actual)
    rows = []
    for e in expected:
        names = [plain(n) for n in e.get("match") or [e["provider"]]]
        found = next((a for a in left if a["date"] == e["date"] and any(n in plain(a["provider"]) for n in names)
                      and (not a.get("member") or not e.get("member") or a["member"] == e["member"])), None)
        problems = []
        if found is None:
            problems.append("no such visit in the app")
        else:
            left.remove(found)
            if found["owed"] != e["owed"]:
                problems.append(f"owed {money(found['owed'])}, expected {money(e['owed'])}")
            if e.get("paid") is not None and found["paid"] != e["paid"]:
                problems.append(f"paid {money(found['paid'])}, expected {money(e['paid'])}")
            if e.get("accept") and found["status"] not in e["accept"]:
                problems.append(f"status {found['label']}, expected {e['expected']}")
        rows.append({**e, "actual": found, "problems": problems, "ok": not problems})
    return rows, left


def money(c: int | None) -> str:
    return "–" if c is None else f"${c / 100:,.2f}"


# ---------- one household, driven over HTTP ----------

@dataclass
class Scenario:
    key: str
    title: str
    family: str  # the plan comes from it
    people: list[dict]
    expected: list[dict]
    exports: list[tuple[str, str]] = field(default_factory=list)  # (file name, text)
    documents: list[str] = field(default_factory=list)  # PDFs in the input folder
    expected_types: dict[str, str] = field(default_factory=dict)


def settings_records(s: Scenario) -> list[tuple[str, str, dict]]:
    from mhs.ingest.resolve import slug

    ids = [f"mbr-{slug(p['name'])}" for p in s.people]
    level, deductible = PLANS[s.family]
    plan = {"id": f"plan-{YEAR}-aegis-hdhp", "plan_year": YEAR, "insurer": "Aegis Health Plans",
            "plan_name": "Aegis HDHP", "coverage_order": "primary", "coverage_start": f"{YEAR}-01-01",
            "coverage_end": f"{YEAR}-12-31", "hsa_eligible_plan": True, "coinsurance_rate": 0.2, "member_ids": ids,
            "limits": [{"type": "deductible", "network": "in_network", "level": level, "amount": deductible}]}
    out = []
    for mid, p in zip(ids, s.people):
        first, *rest = p["name"].split()
        out.append(("member", "member", {"id": mid, "name": p["name"], "relationship": p["relationship"],
                                         "aliases": [p["name"], f"{' '.join(rest)}, {first}"]}))
    return out + [("plan", "plan", plan), ("account", "account", {"id": "acct-hsa", "name": "HSA", "type": "hsa"})]


def set_up(s: Scenario, accounts, stamp: str) -> dict:
    from mhs.data import importer
    from mhs.data.household_store import HouseholdStore
    from mhs.data.money import to_dollars

    household_id = accounts.create_household(f"Harness: {s.title} ({stamp})")
    email = f"{s.key}-{stamp}@example.test"
    password = secrets.token_urlsafe(12)
    _, totp_secret = accounts.add_member(household_id, email, s.people[0]["name"], password)
    store = HouseholdStore(accounts.db, household_id)
    for kind, definition, record in settings_records(s):
        errors = importer.record_errors(definition, to_dollars(record))
        if errors:
            raise SystemExit(f"{s.key}: {kind} is invalid: {'; '.join(errors)}")
        store.upsert(kind, record, edited=True)  # as if entered in Settings
    return {"household_id": household_id, "email": email, "password": password, "totp_secret": totp_secret}


def csrf(page_html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', page_html).group(1)


def alert(page_html: str) -> str:
    m = re.search(r'class="alert bad">\s*([^<]+)<', page_html)
    return html.unescape(m.group(1)).strip() if m else ""


def sign_in(base_url: str, login: dict):
    import httpx
    import pyotp

    c = httpx.Client(base_url=base_url, timeout=120, follow_redirects=False)
    c.post("/signin", data={"email": login["email"], "password": login["password"]})
    r = c.post("/signin/mfa", data={"code": pyotp.TOTP(login["totp_secret"]).now(),
                                    "csrf_token": csrf(c.get("/signin/mfa").text)})
    if r.status_code != 303:
        raise SystemExit(f"{login['email']} couldn't sign in: {r.status_code} {alert(r.text)}")
    return c, csrf(c.get("/uploads").text)


def import_export(c, token: str, name: str, text: str) -> dict:
    r = c.post("/uploads", data={"csrf_token": token, "kind": "auto"}, files={"file": (name, text.encode(), "text/csv")})
    m = re.search(r'name="token" value="([^"]+)"', r.text)
    if not m:
        return {"file": name, "outcome": "refused", "detail": alert(r.text) or f"HTTP {r.status_code}", "ok": False}
    done = c.post("/import/confirm", data={"token": m.group(1), "csrf_token": token})
    ok = done.status_code == 303
    return {"file": name, "outcome": "imported" if ok else "refused", "detail": "" if ok else alert(done.text), "ok": ok}


def upload_document(c, token: str, folder: Path, name: str, expected_type: str) -> dict:
    from tests.test_r1_scenarios import form_values

    r = c.post("/uploads", data={"csrf_token": token, "kind": "auto"},
               files={"file": (name, (folder / name).read_bytes(), "application/pdf")})
    if r.status_code != 303:
        return {"file": name, "outcome": "refused", "detail": alert(r.text) or f"HTTP {r.status_code}", "ok": False,
                "type": "", "expected_type": expected_type}
    upload_id = r.headers["location"].split("uploaded=")[1]
    deadline = time.monotonic() + WAIT_SECONDS
    while (view := c.get(f"/api/uploads/{upload_id}").json())["status"] not in ("review", "failed", "filed"):
        if time.monotonic() > deadline:
            return {"file": name, "outcome": "timed out", "detail": f"not read in {WAIT_SECONDS}s", "ok": False,
                    "type": "", "expected_type": expected_type}
        time.sleep(0.5)
    row = {"file": name, "type": view.get("doc_type") or "", "expected_type": expected_type, "ok": False, "detail": ""}
    if view["status"] != "review":
        return {**row, "outcome": view["status"], "detail": view.get("error") or ""}
    values = form_values(c.get(f"/uploads/{upload_id}/review").text, f"/uploads/{upload_id}/confirm")
    if not values:
        return {**row, "outcome": "needs you", "detail": "the review page offers nothing to confirm"}
    values["csrf_token"] = token
    done = c.post(f"/uploads/{upload_id}/confirm", data=values)
    where = done.headers.get("location", "")
    if done.status_code == 303:  # confirmed exactly as extracted: nothing is filled in on the member's behalf
        right_type = not expected_type or row["type"] in expected_type.split("|")
        return {**row, "outcome": "confirmed" if right_type else "filed as the wrong type", "detail": where,
                "ok": right_type}
    return {**row, "outcome": "needs you", "detail": alert(done.text) or f"HTTP {done.status_code}"}


def app_visits(db, household_id: str) -> list[dict]:
    from mhs.core.reconcile import build_report
    from mhs.data.household_store import HouseholdStore
    from mhs.data.repository import load_dataset

    report = build_report(load_dataset(HouseholdStore(db, household_id)), YEAR, date.today())
    return [{"id": v.id, "date": v.visit["date"], "provider": v.provider.get("name", ""),
             "member": (v.member or {}).get("name"), "status": v.status, "label": v.status_label,
             "owed": v.responsibility, "paid": v.paid, "findings": [c.name for c in v.findings]}
            for v in report.visits]


def screenshots(browser, base_url: str, client, out: Path, key: str, visits: list[dict]) -> list[str]:
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    context.add_cookies([{"name": n, "value": v, "url": base_url} for n, v in client.cookies.items()])
    page = context.new_page()
    folder = out / "screenshots" / key
    folder.mkdir(parents=True, exist_ok=True)
    taken = []

    def shoot(name: str, path: str) -> None:
        page.goto(base_url + path, wait_until="load")
        page.screenshot(path=str(folder / f"{name}.png"), full_page=True)
        taken.append(f"screenshots/{key}/{name}.png")

    for name, path in PAGES:
        shoot(name, path)
    worth_seeing = sorted(visits, key=lambda v: (not v["findings"], v["status"] == "complete", v["date"]))
    for v in worth_seeing[:MAX_VISIT_SHOTS]:
        shoot(f"visit-{v['id']}", f"/visits/{v['id']}")
    context.close()
    return taken


# ---------- the report ----------

def report_html(results: list[dict], notes: list[str], stamp: str) -> str:
    e = html.escape
    parts = [f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Harness results</title><style>
body{{font:15px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;color:#1c2733;margin:0;background:#f4f6f8}}
main{{max-width:1180px;margin:0 auto;padding:24px}}h1{{margin:0 0 4px}}h2{{margin:32px 0 8px}}h3{{margin:20px 0 6px}}
.muted{{color:#5c6b7a}}.card{{background:#fff;border:1px solid #dde3e9;border-radius:8px;padding:16px;margin:12px 0}}
.tiles{{display:flex;gap:12px;flex-wrap:wrap}}.tile{{background:#f4f6f8;border-radius:6px;padding:10px 14px;min-width:130px}}
.tile b{{display:block;font-size:22px}}table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{text-align:left;padding:5px 8px;border-bottom:1px solid #e6eaee;vertical-align:top}}th{{color:#5c6b7a;font-weight:600}}
td.n,th.n{{text-align:right;white-space:nowrap}}.ok{{color:#16723b;font-weight:600}}.bad{{color:#b3261e;font-weight:600}}
code{{background:#eef1f4;padding:1px 4px;border-radius:3px;user-select:all}}.shots{{display:flex;flex-wrap:wrap;gap:10px}}
.shots a{{width:200px;font-size:12px;color:#1c2733}}.shots img{{width:200px;height:130px;object-fit:cover;
object-position:top;border:1px solid #dde3e9;border-radius:4px;display:block}}</style></head><body><main>
<h1>Test harness results</h1><p class="muted">Run {e(stamp)}. Made-up data from <code>{INPUT}</code>. Every document
was confirmed automatically, exactly as extracted, without a person checking it.</p>"""]
    if notes:
        parts.append('<div class="card"><strong>Notes on the test data</strong><ul>' +
                     "".join(f"<li>{e(n)}</li>" for n in notes) + "</ul></div>")
    for r in results:
        rows, extra = r["comparison"], r["unexpected"]
        good = sum(x["ok"] for x in rows)
        files_ok = sum(f["ok"] for f in r["files"])
        total_owed = sum(v["owed"] or 0 for v in r["visits"])
        total_paid = sum(v["paid"] or 0 for v in r["visits"])
        findings = sum(len(v["findings"]) for v in r["visits"])
        parts.append(f"""<h2>{e(r['title'])}</h2><div class="card"><div class="tiles">
<div class="tile"><b>{files_ok}/{len(r['files'])}</b>files ingested</div>
<div class="tile"><b class="{'ok' if good == len(rows) else 'bad'}">{good}/{len(rows)}</b>visits as expected</div>
<div class="tile"><b>{len(r['visits'])}</b>visits in the app ({len(extra)} unexpected)</div>
<div class="tile"><b>{findings}</b>findings</div><div class="tile"><b>{money(total_owed)}</b>you owe, per the app</div>
<div class="tile"><b>{money(total_paid)}</b>paid, per the app</div></div>
<h3>How to look at it yourself</h3><p>Open <a href="http://127.0.0.1:3063">http://127.0.0.1:3063</a> and sign in with
<code>{e(r['login']['email'])}</code> and password <code>{e(r['login']['password'])}</code>. For the 6-digit code, run
<code>uv run tools/run_harness.py login {e(r['login']['email'])}</code>, which also prints the password, or add authenticator secret
<code>{e(r['login']['totp_secret'])}</code> to an app.</p><h3>Files</h3><table><tr><th>File</th><th>Read as</th>
<th>Should be</th><th>Outcome</th><th>Detail</th></tr>""")
        for f in r["files"]:
            type_ok = not f.get("expected_type") or f.get("type") in f["expected_type"].split("|")
            parts.append(f"<tr><td>{e(f['file'])}</td><td class=\"{'' if type_ok else 'bad'}\">{e(f.get('type', ''))}</td>"
                         f"<td>{e(f.get('expected_type', '').replace('|', ' or '))}</td>"
                         f"<td class=\"{'ok' if f['ok'] else 'bad'}\">{e(f['outcome'])}</td><td>{e(f['detail'])}</td></tr>")
        parts.append("""</table><h3>Expected and actual, per visit</h3><table><tr><th></th><th>Date</th><th>Person</th>
<th>Provider</th><th class="n">Owed: expected</th><th class="n">app</th><th class="n">Paid: expected</th><th class="n">app</th>
<th>Status: expected</th><th>app</th></tr>""")
        for x in rows:
            a = x["actual"] or {}
            parts.append(f"<tr><td class=\"{'ok' if x['ok'] else 'bad'}\">{'✓' if x['ok'] else '✗'}</td><td>{e(x['date'])}</td>"
                         f"<td>{e(x.get('member') or '')}</td><td>{e(x['provider'])}</td><td class=\"n\">{money(x['owed'])}</td>"
                         f"<td class=\"n\">{money(a.get('owed'))}</td><td class=\"n\">{money(x.get('paid'))}</td>"
                         f"<td class=\"n\">{money(a.get('paid'))}</td><td>{e(x.get('expected', ''))}</td>"
                         f"<td>{e(a.get('label', 'not found'))}</td></tr>")
        parts.append("</table>")
        if extra:
            parts.append("<h3>In the app but not expected</h3><table><tr><th>Date</th><th>Person</th><th>Provider</th>"
                         "<th class=\"n\">Owed</th><th>Status</th></tr>" +
                         "".join(f"<tr><td>{e(v['date'])}</td><td>{e(v.get('member') or '')}</td><td>{e(v['provider'])}</td>"
                                 f"<td class=\"n\">{money(v['owed'])}</td><td>{e(v['label'])}</td></tr>" for v in extra) +
                         "</table>")
        flagged = [v for v in r["visits"] if v["findings"]]
        if flagged:
            parts.append("<h3>What the app flagged</h3><table><tr><th>Date</th><th>Person</th><th>Provider</th>"
                         "<th>Findings</th></tr>" +
                         "".join(f"<tr><td>{e(v['date'])}</td><td>{e(v.get('member') or '')}</td><td>{e(v['provider'])}</td>"
                                 f"<td>{e('; '.join(v['findings']))}</td></tr>" for v in flagged) + "</table>")
        parts.append('<h3>Screenshots</h3><div class="shots">' +
                     "".join(f'<a href="{e(s)}"><img src="{e(s)}" alt="{e(Path(s).stem)}">{e(Path(s).stem)}</a>'
                             for s in r["screenshots"]) + "</div></div>")
    parts.append("</main></body></html>")
    return "".join(parts)


# ---------- inside the tests container ----------

def scenarios(folder: Path) -> tuple[list[Scenario], list[str]]:
    from tools.make_harness_pdfs import documents

    masters = sorted(folder.glob("*.csv"))
    if len(masters) != 1:
        raise SystemExit(f"Expected one CSV in {folder}, found {len(masters)}.")
    rows = read_master(masters[0].read_text(encoding="utf-8-sig"))
    out = []
    pdfs = {p.name for p in (folder / "pdfs").glob("*.pdf")}
    pages = documents(rows)
    missing = set(pages) - pdfs
    if missing:
        raise SystemExit(f"Missing PDFs: run `uv run tools/make_harness_pdfs.py`. {sorted(missing)[:3]}")
    for family in dict.fromkeys(r["Family"] for r in rows):
        part = [r for r in rows if r["Family"] == family]
        key = family.removeprefix("The ").lower()
        expected = expected_visits(part)
        out.append(Scenario(f"csv-{key}", f"{family}, from the CSV", family, members_of(part), expected,
                            exports=[(f"{key}-claims.csv", claims_csv(part)), (f"{key}-hsa.csv", hsa_csv(part))]))
        names = list(dict.fromkeys(r["Provider_Invoice_Asset_PDF"] for r in part))
        names += [part[0]["Insurance_EOB_Asset_PDF"], part[0]["HSA_Statement_Asset_PDF"]]
        out.append(Scenario(f"pdf-{key}", f"{family}, from the PDFs", family, members_of(part),
                            expected_from_invoices(part, pages), documents=names,
                            expected_types={n: expected_type(n) for n in names}))
        # Everything together, as a member would use it: the bills as PDFs, then the insurer's and HSA's exports.
        facility = {(r["Date_of_Service"], r["Provider_Name"], r["Member_Name"]): r["Facility_Name"] for r in part}
        out.append(Scenario(f"all-{key}", f"{family}, invoices and exports together", family, members_of(part),
                            [{**e, "match": [e["provider"], facility[(e["date"], e["provider"], e["member"])]]}
                             for e in expected],
                            exports=[(f"{key}-claims.csv", claims_csv(part)), (f"{key}-hsa.csv", hsa_csv(part))],
                            documents=[n for n in names if n.startswith("invoice_")],
                            expected_types={n: expected_type(n) for n in names}))
    return out, DATA_NOTES


def inside(args) -> int:
    from playwright.sync_api import sync_playwright

    from mhs.web.household.admin import accounts_from_env

    folder, out = Path(args.input), Path(args.output)
    for old in out.glob("screenshots/*/*.png"):
        old.unlink()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stack_url = os.environ.get("MHS_STACK_URL", "http://app:3063")
    browser_url = f"http://localhost:{urlsplit(stack_url).port}"
    plan, notes = scenarios(folder)
    db, accounts = accounts_from_env()
    results = []
    with sync_playwright() as p:
        # The app's headers ask browsers to upgrade to HTTPS except on localhost, so the browser calls the stack that.
        browser = p.chromium.launch(args=[f"--host-resolver-rules=MAP localhost {urlsplit(stack_url).hostname}"])
        for s in plan:
            print(f"== {s.title}", flush=True)
            login = set_up(s, accounts, stamp)
            client, token = sign_in(stack_url, login)
            files = []
            for name in s.documents:
                files.append(upload_document(client, token, folder / "pdfs", name, s.expected_types.get(name, "")))
                print(f"   {name}: {files[-1]['outcome']}", flush=True)
            files += [import_export(client, token, n, t) for n, t in s.exports]
            visits = app_visits(db, login["household_id"])
            rows, extra = compare(s.expected, visits)
            shots = screenshots(browser, browser_url, client, out, s.key, visits)
            client.close()
            print(f"   {sum(f['ok'] for f in files)}/{len(files)} files, {sum(x['ok'] for x in rows)}/{len(rows)} "
                  f"visits as expected, {len(extra)} unexpected", flush=True)
            results.append({**asdict(s), "login": login, "files": files, "visits": visits, "comparison": rows,
                            "unexpected": extra, "screenshots": shots})
        (out / "results.json").write_text(json.dumps(results, indent=2))
        (out / "logins.json").write_text(json.dumps({r["login"]["email"]: r["login"] for r in results}, indent=2))
        report = out / "report.html"
        report.write_text(report_html(results, notes, stamp))
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(report.resolve().as_uri(), wait_until="load")
        page.screenshot(path=str(out / "results.png"), full_page=True)
        browser.close()
    db.close()
    return 0 if not args.strict or all(x["ok"] for r in results for x in r["comparison"]) else 1


# ---------- on your machine ----------

def show_login(email: str, output: Path) -> int:
    import pyotp

    path = output / "logins.json"
    if not path.exists():
        print(f"No {path}: run the harness first.")
        return 1
    logins = json.loads(path.read_text())
    if email not in logins:
        print("Harness members:", ", ".join(logins))
        return 1
    print(f"email:    {email}\npassword: {logins[email]['password']}\ncode:     "
          f"{pyotp.TOTP(logins[email]['totp_secret']).now()} (changes every 30 seconds)")
    return 0


def on_host(args) -> int:
    folder, out = (ROOT / args.input).resolve(), (ROOT / args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.chmod(out, 0o777)  # the container's user writes here
    compose = ["docker", "compose", "--profile", "test"]
    subprocess.run([*compose, "build", "app", "tests"], cwd=ROOT, check=True)
    subprocess.run([*compose, "up", "-d", "--wait", "app", "worker"], cwd=ROOT, check=True)
    command = [*compose, "run", "--rm", "--no-TTY", "-v", f"{folder}:/harness/in:ro", "-v", f"{out}:/harness/out",
               "tests", "python", "tools/run_harness.py", "--inside", "--input", "/harness/in", "--output", "/harness/out"]
    if args.strict:
        command.append("--strict")
    code = subprocess.run(command, cwd=ROOT).returncode
    if (out / "results.png").exists():
        print(f"\nResults screenshot: {out / 'results.png'}\nFull report, with logins: {out / 'report.html'}\n"
              "The stack is still running: http://127.0.0.1:3063 (stop it with `docker compose stop`).")
    return code


def main() -> None:
    if sys.argv[1:2] in (["login"], ["code"]):  # `code` is what earlier reports print
        sys.exit(show_login(sys.argv[2] if len(sys.argv) > 2 else "", ROOT / OUTPUT))
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", default=INPUT)
    parser.add_argument("--output", default=OUTPUT)
    parser.add_argument("--strict", action="store_true", help="exit 1 when a visit isn't as expected")
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.inside:
        sys.path[:0] = [str(ROOT), str(ROOT / "src")]
        sys.exit(inside(args))
    sys.exit(on_host(args))


if __name__ == "__main__":
    main()
