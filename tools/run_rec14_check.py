"""Import samples/rec14 into a running stack and check each visit's page against samples/rec14/TEST_PLAN.md.

    uv run tools/run_rec14_check.py                     # the stack on http://127.0.0.1:3063
    uv run tools/run_rec14_check.py login               # the last run's address, email, password and current code

Creates a new household, signs in and works as a member would, reading what the pages show. Writes
harness-output/rec14/: results.md, the login and screenshots. Exit code 1 if anything isn't as expected. To test beside
a running stack, pass --url and --compose with the extra `docker compose` arguments. Synthetic data only.
"""

import argparse
import html
import json
import re
import secrets
import shlex
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import pyotp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FOLDER = ROOT / "samples" / "rec14"
OUTPUT = ROOT / "harness-output" / "rec14"
SIDEWAYS = "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"


def words(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def csrf(page: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)


def blocks(page: str, result: str) -> list[dict]:
    """The checks of one result on a visit page: name, wording and the code and amount its close form posts."""
    out = []
    for part in re.split(r'(?=<div class="check )', page):
        if part.startswith(f'<div class="check {result}"'):
            name = re.search(r"<strong>([^<]+)</strong>", part)
            out.append({"name": html.unescape(name.group(1)) if name else "", "text": words(part),
                        "code": (re.search(r'name="code" value="([^"]+)"', part) or [None, ""])[1],
                        "amount": (re.search(r'name="amount" value="([^"]+)"', part) or [None, ""])[1]})
    return out


def row_of(page: str, visit_id: str) -> dict:
    m = re.search(rf'<a class="visit-row[^"]*" href="/visits/{visit_id}">(.*?)</a>', page, re.S)
    if not m:
        return {}
    badge = re.search(r'class="badge[^"]*">([^<]+)<', m.group(1))
    issue = re.search(r'class="bad-ink">\$([\d,.]+)<', m.group(1))
    chip = re.search(r"Worth a closer look: (\d+)", m.group(1))
    return {"status": badge.group(1).strip() if badge else "", "at_issue": round(float(issue.group(1).replace(",", "")) * 100) if issue else 0,
            "chip": int(chip.group(1)) if chip else 0}


def set_up(compose: list[str], stamp: str) -> dict:
    run = lambda *args, **kw: subprocess.run([*compose, "exec", "-T", "app", "mhs-admin", *args], cwd=ROOT, text=True,  # noqa: E731
                                             capture_output=True, check=True, **kw).stdout
    household = re.search(r"[0-9a-f-]{36}", run("create-household", f"REC-14 test ({stamp})")).group(0)
    email, password = f"rec14-{stamp}@example.test", secrets.token_hex(10)
    out = run("add-member", "--household", household, "--email", email, "--name", "Riley Test", "--password-stdin",
              input=password + "\n")
    return {"household_id": household, "email": email, "password": password,
            "totp_secret": re.search(r"secret:\s+(\S+)", out).group(1)}


def sign_in(url: str, login: dict) -> tuple[httpx.Client, str]:
    c = httpx.Client(base_url=url, timeout=120, follow_redirects=False)
    c.post("/signin", data={"email": login["email"], "password": login["password"]})
    r = c.post("/signin/mfa", data={"code": pyotp.TOTP(login["totp_secret"]).now(), "csrf_token": csrf(c.get("/signin/mfa").text)})
    if r.status_code != 303:
        sys.exit(f"Couldn't sign in: {r.status_code}")
    return c, csrf(c.get("/uploads").text)


def import_file(c: httpx.Client, token: str) -> str:
    preview = c.post("/import", data={"csrf_token": token},
                     files={"file": ("rec14-ingest.json", (FOLDER / "rec14-ingest.json").read_bytes(), "application/json")})
    m = re.search(r'name="token" value="([^"]+)"', preview.text)
    if not m:
        sys.exit("The import was refused: " + words(preview.text)[:600])
    done = c.post("/import/confirm", data={"token": m.group(1), "csrf_token": token})
    return f"{done.status_code} {done.headers.get('location', '')}"


def unconfirmed_upload(c: httpx.Client, token: str) -> str:
    """TC-REC-14-8: an EOB for the next visit, read by the worker and left waiting for review."""
    from tests.pdfs import make_pdf

    text = """Test Insurer
EXPLANATION OF BENEFITS
THIS IS NOT A BILL
Patient: Riley Test
Provider: Case Eight Unconfirmed
Claim number: CLM-UNCONFIRMED
Date of service: 03/15/2026
Processed date: 03/25/2026
Date Code Description Billed Allowed Plan paid You owe
03/15/2026 96413 Treatment $500.00 $250.00 $0.00 $250.00
Amount billed: $500.00
Allowed amount: $250.00
Plan paid: $0.00
You owe: $250.00
"""
    r = c.post("/uploads", data={"csrf_token": token, "kind": "eob"},
               files={"file": ("unconfirmed-eob.pdf", make_pdf(text), "application/pdf")})
    upload_id = r.headers["location"].split("uploaded=")[1]
    deadline = time.monotonic() + 180
    while (status := c.get(f"/api/uploads/{upload_id}").json()["status"]) not in ("review", "failed"):
        if time.monotonic() > deadline:
            return "timed out"
        time.sleep(0.5)
    return status


def uploaded_documents(c: httpx.Client, token: str) -> dict[str, list[str]]:
    """The real upload path: PDFs read by the worker and confirmed as read, with nothing typed for the member. Each pair
    is the same treatment with a changed price, so REC-14 should flag the second visit. Imported files skip this."""
    from tests.pdfs import make_pdf
    from tests.test_r1_scenarios import form_values

    def eob(provider, when, claim, allowed):
        us = f"{when[5:7]}/{when[8:]}/{when[:4]}"
        return f"""Test Insurer
EXPLANATION OF BENEFITS
THIS IS NOT A BILL
Patient: Riley Test
Provider: {provider}
Claim number: {claim}
Date of service: {us}
Processed date: {us}
Date Code Description Billed Allowed Plan paid You owe
{us} 96413 Treatment $500.00 ${allowed}.00 $0.00 ${allowed}.00
Amount billed: $500.00
Plan discount: ${500 - allowed}.00
Allowed amount: ${allowed}.00
Plan paid: $0.00
Deductible: ${allowed}.00
You owe: ${allowed}.00
"""

    def statement(provider, when, charge):
        us = f"{when[5:7]}/{when[8:]}/{when[:4]}"
        return f"""{provider}
PATIENT STATEMENT
Statement date: {us}
Account number: 4411
Patient: Test, Riley
Date Code Description Charges Insurance Adjustments Payments Balance
{us} 96413 Treatment ${charge}.00 $0.00 $0.00 $0.00 ${charge}.00
Total charges: ${charge}.00
Insurance payments: $0.00
Amount due: ${charge}.00
"""

    def send(name, text):
        r = c.post("/uploads", data={"csrf_token": token, "kind": "auto"},
                   files={"file": (name, make_pdf(text), "application/pdf")})
        if r.status_code != 303:
            return f"{name}: refused ({words(r.text)[-200:]})"
        upload_id = r.headers["location"].split("uploaded=")[1]
        deadline = time.monotonic() + 180
        while (status := c.get(f"/api/uploads/{upload_id}").json()["status"]) not in ("review", "failed"):
            if time.monotonic() > deadline:
                return f"{name}: not read"
            time.sleep(0.5)
        values = form_values(c.get(f"/uploads/{upload_id}/review").text, f"/uploads/{upload_id}/confirm")
        values["csrf_token"] = token
        done = c.post(f"/uploads/{upload_id}/confirm", data=values)
        return done.headers.get("location", "") if done.status_code == 303 else f"{name}: {status}, {done.status_code}"

    stamp = str(int(time.time()))[-5:]  # a rerun's PDFs are new files, not duplicates
    out = {}
    first = send("up-eob-1.pdf", eob(f"Upload Eob Clinic {stamp}", "2026-06-01", f"UP-1-{stamp}", 400))
    second = send("up-eob-2.pdf", eob(f"Upload Eob Clinic {stamp}", "2026-07-01", f"UP-2-{stamp}", 250))
    out["Uploaded EOBs"] = uploaded_result(c, first, second, "Allowed amount changed")
    first = send("up-st-1.pdf", statement(f"Upload Statement Clinic {stamp}", "2026-06-02", 400))
    second = send("up-st-2.pdf", statement(f"Upload Statement Clinic {stamp}", "2026-07-02", 250))
    out["Uploaded statements"] = uploaded_result(c, first, second, "Billed amount changed")
    return out


def uploaded_result(c: httpx.Client, first: str, second: str, name: str) -> list[str]:
    if not (first.startswith("/visits/") and second.startswith("/visits/")):
        return [f"not confirmed: {first} / {second}"]
    if first == second:
        return [f"both went onto one visit, {first}"]
    found = [b["name"] for b in blocks(c.get(second).text, "flag")]
    return [] if found == [name] else [f"{second} flags {found}, expected {[name]}"]


def check_visit(c: httpx.Client, vid: str, want: dict, rows: dict) -> list[str]:
    page = c.get(f"/visits/{vid}").text
    problems = []
    for kind, result, label in (("flags", "flag", "flag"), ("notes", "info", "note")):
        found = [b for b in blocks(page, result) if kind == "flags" or "share" in b["name"].lower()]
        if sorted(b["name"] for b in found) != sorted(f["name"] for f in want[kind]):
            problems.append(f"{label}s: {[b['name'] for b in found]}, expected {[f['name'] for f in want[kind]]}")
            continue
        for f in want[kind]:
            text = next(b["text"] for b in found if b["name"] == f["name"])
            problems += [f"{label} {f['name']!r} doesn't say {w!r}" for w in f["contains"] if w not in text]
    row = rows.get(vid) or {}
    if want["status"] and row.get("status") != want["status"]:
        problems.append(f"status {row.get('status')!r}, expected {want['status']!r}")
    if want["at_issue"] is not None and row.get("at_issue") != want["at_issue"]:
        problems.append(f"at issue {row.get('at_issue')}, expected {want['at_issue']}")
    if row.get("chip", 0) != len(want["flags"]):
        problems.append(f"the Visits row says {row.get('chip', 0)} to look at, expected {len(want['flags'])}")
    return problems


def browser_checks(url: str, c: httpx.Client, out: Path) -> list[tuple[str, list[str]]]:
    from playwright.sync_api import sync_playwright

    results = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for label, device in (("375px", {"viewport": {"width": 375, "height": 812}, "is_mobile": True, "has_touch": True}),
                              ("1280px", {"viewport": {"width": 1280, "height": 800}})):
            context = b.new_context(**device)
            context.add_cookies([{"name": n, "value": v, "url": url} for n, v in c.cookies.items()])
            page = context.new_page()
            errors = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            problems = []
            page.goto(f"{url}/visits/v-tc1-b", wait_until="load")
            text = page.locator("#findings").inner_text()
            problems += [f"missing {w!r}" for w in ("Feb 2, 2026", "Mar 2, 2026", "$400.00", "$250.00", "$150.00", "a new contract",
                                                    "Compare the two visits") if w not in text]
            if page.evaluate(SIDEWAYS) > 1:
                problems.append("the page scrolls sideways")
            link = page.get_by_role("link", name="See the earlier visit")
            if link.count() != 1 or not link.first.is_visible():
                problems.append("no link to the earlier visit")
            problems += [f"browser error: {e[:120]}" for e in errors]
            page.locator("#findings").screenshot(path=str(out / f"flag-{label}.png"))
            page.goto(f"{url}/visits?year=2026&repeat=1", wait_until="load")
            page.screenshot(path=str(out / f"visits-{label}.png"), full_page=True)
            if page.evaluate(SIDEWAYS) > 1:
                problems.append("Visits scrolls sideways")
            results.append((label, problems))
            context.close()
        b.close()
    return results


def show_login() -> None:
    login = json.loads((OUTPUT / "login.json").read_text())
    print(f"address:  {login['url']}\nemail:    {login['email']}\npassword: {login['password']}\n"
          f"code:     {pyotp.TOTP(login['totp_secret']).now()} (changes every 30 seconds)")


def main() -> None:
    if sys.argv[1:2] == ["login"]:
        return show_login()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:3063")
    parser.add_argument("--compose", default="", help="extra `docker compose` arguments, for a stack beside the main one")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    expected = json.loads((FOLDER / "rec14-expected.json").read_text())
    login = set_up(["docker", "compose", *shlex.split(args.compose)], stamp)
    (OUTPUT / "login.json").write_text(json.dumps({"url": args.url, **login}, indent=2))
    c, token = sign_in(args.url, login)
    print("Import:", import_file(c, token))
    print("Unconfirmed upload:", unconfirmed_upload(c, token))

    def rows_now() -> dict:
        pages = [c.get(f"/visits?year={y}&member=&sort=oldest").text for y in (2025, 2026)]
        return {vid: row for vid in expected for row in [next((r for r in (row_of(p, vid) for p in pages) if r), {})]}

    results = {}
    rows = rows_now()
    for vid, want in expected.items():
        results.setdefault(want["case"], []).append((vid, check_visit(c, vid, want, rows)))

    extra = {}
    # A flag can't move the status or the dollars: every flagged visit is compared with the same case's unflagged visits above.
    only = c.get("/visits?year=2026&member=&repeat=1").text
    listed = set(re.findall(r'class="visit-row[^"]*" href="/visits/([^"]+)"', only))
    flagged = {v for v, w in expected.items() if w["flags"]}
    extra["Worth a closer look filter"] = [] if listed == flagged else [f"listed {sorted(listed ^ flagged)} wrongly"]
    visits_2026 = c.get("/visits?year=2026&member=").text
    extra["TC-REC-14-8 no visit from the unconfirmed upload"] = (
        [] if len(re.findall(r'class="visit-row s-edge', visits_2026)) == sum(w["date"] < "2026-" or w["date"][:4] == "2026" for w in expected.values()) - 1
        else ["the unconfirmed upload changed the visit count"])

    # TC-REC-14-9: close the flag as wrong; it stays closed after a re-import and counts on Finding accuracy.
    [block] = blocks(c.get("/visits/v-tc9-3").text, "flag")
    closed = c.post("/visits/v-tc9-3/findings", data={"csrf_token": token, "code": block["code"], "amount": block["amount"],
                                                      "verdict": "wrong", "reason": "New contract, as expected"})
    page = c.get("/visits/v-tc9-3").text
    problems = [] if closed.status_code in (200, 303) else [f"closing returned {closed.status_code}"]
    problems += [] if not blocks(page, "flag") and blocks(page, "closed") else ["not closed after closing"]
    import_file(c, token)
    page = c.get("/visits/v-tc9-3").text
    problems += [] if not blocks(page, "flag") and blocks(page, "closed") else ["came back after a re-import"]
    accuracy = words(c.get("/accuracy?year=2026").text)
    problems += [] if re.search(r"Repeat service \d+ [1-9]", accuracy) or re.search(r"Repeat service 0 1", accuracy) else [f"not on Finding accuracy: {accuracy[:300]}"]
    extra["TC-REC-14-9 close as wrong, re-import, Finding accuracy"] = problems

    extra.update(uploaded_documents(c, token))
    for label, problems in browser_checks(args.url, c, OUTPUT):
        extra[f"TC-REC-14-10 at {label}"] = problems
    c.close()

    lines = [f"# REC-14 results, {stamp}", "", f"App: {args.url}. Household member: `{login['email']}` (password in login.json).", "",
             "| Case | Visits | Result | Detail |", "| --- | --- | --- | --- |"]
    failed = 0
    for case, items in results.items():
        bad = [f"{v}: {'; '.join(p)}" for v, p in items if p]
        failed += bool(bad)
        lines.append(f"| {case} | {len(items)} | {'Fail' if bad else 'Pass'} | {' / '.join(bad)} |")
    for case, problems in extra.items():
        failed += bool(problems)
        lines.append(f"| {case} | | {'Fail' if problems else 'Pass'} | {'; '.join(problems)} |")
    (OUTPUT / "results.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
