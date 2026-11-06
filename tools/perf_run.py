"""Time typical uploads from upload to a reconciled visit on the running stack (PLT-05, TC-PLT-05-1).

    docker compose --profile test run --rm tests python tools/perf_run.py --n 50

Runs inside the compose `tests` container (it enrolls a throwaway member straight in the stack's database, like the
stack tests). Each upload goes one at a time: the upload request, reading and scrubbing in the app tier, the
worker's extraction, then the confirm request. Machine time is everything except the member's own review: the
time between the review being ready and the member pressing Confirm isn't counted. Documents are synthetic: the
development corpus's EOBs and statements as PDFs, some as 2 to 3 page PDFs, and some as phone photos read by OCR.
"""

import argparse
import json
import re
import secrets
import statistics
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

TARGET_SECONDS = 60


def documents(n: int) -> list[tuple[str, bytes, str]]:
    """n typical uploads: (file name, bytes, content type)."""
    from tests.pdfs import make_image, make_pdf
    from mhs.ingest.text import read_pdf

    texts = []
    for truth in sorted((ROOT / "tests" / "corpus").glob("*.json")):
        if json.loads(truth.read_text())["doc_type"] in ("eob", "provider_statement"):
            text = "\n".join(read_pdf(truth.with_suffix(".pdf").read_bytes()))
            texts.append(text.replace("\u2019", "'").encode("latin-1", "replace").decode("latin-1"))
    out = []
    for i in range(n):
        text = texts[i % len(texts)] + f"\nReference {uuid.uuid4().hex[:8]}"  # every upload is a new file
        if i % 5 == 4:
            out.append((f"photo-{i:02d}.png", make_image(text), "image/png"))  # one in five is a phone photo
        elif i % 5 == 3:
            pages = [text] + ["Page continued: notes and messages from your plan."] * (1 + i % 2)
            out.append((f"doc-{i:02d}.pdf", make_pdf(*pages), "application/pdf"))  # 2 or 3 pages
        else:
            out.append((f"doc-{i:02d}.pdf", make_pdf(text), "application/pdf"))
    return out


def run(n: int, base_url: str, timeout: float = 120) -> list[dict]:
    import httpx
    import pyotp

    from mhs.web.household.admin import accounts_from_env
    from tests.test_r1_scenarios import form_values

    db, accounts = accounts_from_env()
    hid = accounts.create_household(f"Performance run {uuid.uuid4().hex[:6]}")
    password = secrets.token_urlsafe(18)
    member, totp_secret = accounts.add_member(hid, f"perf-{uuid.uuid4().hex[:8]}@example.test", "Perf Member", password)
    db.close()
    c = httpx.Client(base_url=base_url, timeout=timeout, follow_redirects=False)

    def csrf(html: str) -> str:
        return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

    c.post("/signin", data={"email": member.email, "password": password})
    c.post("/signin/mfa", data={"code": pyotp.TOTP(totp_secret).now(), "csrf_token": csrf(c.get("/signin/mfa").text)})
    token = csrf(c.get("/uploads").text)
    c.post("/settings/plans", data={"plan_year": "2026", "insurer": "Example Health", "plan_name": "Medical",
                                    "csrf_token": token})
    results = []
    for name, data, ctype in documents(n):
        t0 = time.monotonic()
        r = c.post("/uploads", data={"csrf_token": token, "kind": "auto"}, files={"file": (name, data, ctype)})
        upload_id = r.headers["location"].split("uploaded=")[1]
        while (status := c.get(f"/api/uploads/{upload_id}").json()["status"]) not in ("review", "failed"):
            if time.monotonic() - t0 > timeout:
                raise TimeoutError(f"{name} wasn't read within {timeout} seconds")
            time.sleep(0.2)
        ready = time.monotonic()
        review = c.get(f"/uploads/{upload_id}/review").text  # the member reads and confirms: not machine time
        values = form_values(review, f"/uploads/{upload_id}/confirm")
        values["csrf_token"] = token
        if not values.get("provider"):
            values["provider"] = "Performance Run Clinic"
        if not values.get("service_start"):  # a statement without service lines asks the member for the date
            values["service_start"] = values.get("statement_date") or "2026-06-01"
        t1 = time.monotonic()
        confirm = c.post(f"/uploads/{upload_id}/confirm", data=values)
        done = time.monotonic()
        visit_ok = confirm.status_code == 303 and confirm.headers.get("location", "").startswith("/visits/")
        error = re.search(r'class="alert bad">([^<]+)<', confirm.text) if not visit_ok else None
        results.append({"file": name, "status": status, "confirmed": visit_ok, "error": error.group(1) if error else "",
                        "machine_seconds": round((ready - t0) + (done - t1), 3), "read_seconds": round(ready - t0, 3)})
    c.close()
    return results


def summary(results: list[dict]) -> dict:
    times = sorted(r["machine_seconds"] for r in results)
    p95 = times[max(0, int(round(0.95 * len(times))) - 1)]
    return {"uploads": len(results), "confirmed": sum(r["confirmed"] for r in results),
            "p50_seconds": statistics.median(times), "p95_seconds": p95, "max_seconds": times[-1],
            "target_seconds": TARGET_SECONDS, "meets_target": p95 < TARGET_SECONDS}


def main() -> None:
    import os

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--url", default=os.environ.get("MHS_STACK_URL", "http://app:3063"))
    args = parser.parse_args()
    results = run(args.n, args.url)
    for r in results:
        print(f"{r['file']:16} {r['status']:7} confirmed={r['confirmed']!s:5} machine={r['machine_seconds']:6.2f}s "
              f"{r['error']}")
    s = summary(results)
    print(json.dumps(s, indent=2))
    sys.exit(0 if s["meets_target"] and s["confirmed"] == s["uploads"] else 1)


if __name__ == "__main__":
    main()
