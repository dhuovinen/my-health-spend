"""Insurer connection through the CMS Patient Access API: SMART on FHIR, CARIN Blue Button (ING-09, ADR-054).

Runs in the application tier. The access token is used for one pull and dropped; nothing from the payer is kept
except the claims mapped into an ingest file, which the member reviews like any import. Patient names and member
ids in the bundle are never copied: the member says which household member the pull is for.
"""

import base64
import hashlib
import json
import re
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode

import httpx

from mhs.data.money import dollars
from mhs.ingest.resolve import Providers

SCOPES = "launch/patient patient/ExplanationOfBenefit.read patient/Coverage.read openid fhirUser"
RETRIES = 3
TIMEOUT = 20
CATEGORY = {  # CARIN Blue Button adjudication categories -> ingest EOB fields
    "submitted": "billed", "eligible": "allowed", "benefit": "insurer_paid", "paidtoprovider": "_paid_to_provider",
    "deductible": "deductible", "copay": "copay", "coinsurance": "coinsurance", "noncovered": "not_covered",
    "memberliability": "patient_responsibility", "discount": "adjustment",
}
MONEY_FIELDS = ("billed", "allowed", "insurer_paid", "deductible", "copay", "coinsurance", "not_covered",
                "patient_responsibility", "adjustment")


class FhirError(Exception):
    """The pull couldn't be completed. Carries no response body."""


@dataclass(frozen=True)
class Payer:
    name: str  # short id used in URLs
    label: str
    fhir_base: str
    authorize_url: str
    token_url: str
    client_id: str
    client_secret: str = ""


def payers_from(value: str | None, secret=lambda name: None) -> tuple[Payer, ...]:
    """MHS_FHIR_PAYERS: a JSON list of payers, inline or in a file it names. A confidential client's secret is
    MHS_FHIR_<NAME>_SECRET (or _FILE), else the entry's client_secret; keep either out of git."""
    value = (value or "").strip()
    if value.startswith("["):
        entries = json.loads(value)
    elif value and Path(value).is_file():
        entries = json.loads(Path(value).read_text())
    else:
        return ()
    out = []
    for p in entries:
        name = re.sub(r"[^a-z0-9-]", "", p["name"].lower())
        out.append(Payer(name, p.get("label", name), p["fhir_base"].rstrip("/"), p["authorize_url"], p["token_url"],
                         p["client_id"], secret(f"FHIR_{name.upper().replace('-', '_')}_SECRET")
                         or p.get("client_secret", "")))
    return tuple(out)


# ---------- authorization (SMART App Launch, standalone, PKCE) ----------

@dataclass(frozen=True)
class Flow:
    payer: str
    state: str
    verifier: str
    for_member: str  # the household member record the pull is for

    @staticmethod
    def new(payer: str, for_member: str) -> "Flow":
        return Flow(payer, secrets.token_urlsafe(32), secrets.token_urlsafe(48), for_member)

    def to_cookie(self) -> str:
        return ".".join((self.payer, self.state, self.verifier, self.for_member))

    @staticmethod
    def from_cookie(value: str | None) -> "Flow | None":
        parts = (value or "").split(".")
        return Flow(*parts) if len(parts) == 4 and all(parts[:3]) else None


def authorization_url(payer: Payer, flow: Flow, redirect_uri: str) -> str:
    challenge = base64.urlsafe_b64encode(hashlib.sha256(flow.verifier.encode()).digest()).rstrip(b"=").decode()
    return payer.authorize_url + "?" + urlencode({
        "response_type": "code", "client_id": payer.client_id, "redirect_uri": redirect_uri, "scope": SCOPES,
        "state": flow.state, "aud": payer.fhir_base, "code_challenge": challenge, "code_challenge_method": "S256",
    })


@dataclass
class Grant:
    access_token: str
    patient: str


def exchange(payer: Payer, flow: Flow, code: str, redirect_uri: str, client: httpx.Client) -> Grant:
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
            "client_id": payer.client_id, "code_verifier": flow.verifier}
    if payer.client_secret:
        data["client_secret"] = payer.client_secret
    try:
        r = client.post(payer.token_url, data=data, headers={"Accept": "application/json"}, timeout=TIMEOUT)
        body = r.json() if r.status_code == 200 else {}
    except (httpx.HTTPError, ValueError):
        raise FhirError("The insurer didn't complete the sign-in.") from None
    token, patient = body.get("access_token"), body.get("patient")
    if not isinstance(token, str) or not isinstance(patient, str) or not re.fullmatch(r"[A-Za-z0-9\-.]{1,64}", patient):
        raise FhirError("The insurer didn't complete the sign-in.")
    return Grant(token, patient)


# ---------- the pull ----------

def _get(client: httpx.Client, url: str, token: str, params: dict | None, sleep) -> dict:
    """GET with bounded retries on 429 and 5xx (TC-ING-09-5); 401 means the consent ended."""
    for attempt in range(RETRIES + 1):
        try:
            r = client.get(url, params=params, timeout=TIMEOUT,
                           headers={"Authorization": f"Bearer {token}", "Accept": "application/fhir+json"})
        except httpx.HTTPError:
            r = None
        if r is not None and r.status_code == 200:
            try:
                return r.json()
            except ValueError:
                raise FhirError("The insurer sent something that isn't FHIR.") from None
        if r is not None and r.status_code in (401, 403):
            raise FhirError("The insurer refused the request: access may have been withdrawn. Connect again to "
                            "give permission.")
        if attempt == RETRIES:
            break
        wait = 2 ** attempt
        if r is not None and (after := r.headers.get("Retry-After", "")).isdigit():
            wait = min(int(after), 30)
        sleep(wait)
    raise FhirError(f"The insurer didn't answer after {RETRIES + 1} tries. Nothing was imported; try again later.")


def pull(payer: Payer, grant: Grant, client: httpx.Client, sleep=time.sleep, max_pages: int = 50) -> list[dict]:
    """Every ExplanationOfBenefit for the patient, following the bundle's next links on the payer's host only."""
    url, params = f"{payer.fhir_base}/ExplanationOfBenefit", {"patient": grant.patient, "_count": "50"}
    out = []
    for _ in range(max_pages):
        bundle = _get(client, url, grant.access_token, params, sleep)
        out += [e["resource"] for e in bundle.get("entry") or []
                if (e.get("resource") or {}).get("resourceType") == "ExplanationOfBenefit"]
        nxt = next((l.get("url") for l in bundle.get("link") or [] if l.get("relation") == "next"), None)
        if not nxt or not nxt.startswith(payer.fhir_base + "/"):
            break
        url, params = nxt, None
    return out


# ---------- mapping (TC-ING-09-2) ----------

def _cents(money: dict | None) -> int | None:
    if not isinstance(money, dict) or not isinstance(money.get("value"), (int, float)):
        return None
    return round(money["value"] * 100)


def _categories(adjudications: list[dict]) -> tuple[dict[str, int], list[str]]:
    amounts: dict[str, int] = {}
    codes: list[str] = []
    for a in adjudications or []:
        for coding in (a.get("category") or {}).get("coding") or []:
            name = CATEGORY.get(coding.get("code"))
            cents = _cents(a.get("amount"))
            if name and cents is not None:
                amounts[name] = amounts.get(name, 0) + cents
        for coding in (a.get("reason") or {}).get("coding") or []:
            if coding.get("code"):
                codes.append(str(coding["code"]))
    paid = amounts.pop("_paid_to_provider", None)
    if paid is not None and "insurer_paid" not in amounts:  # "benefit" wins when the payer sends both
        amounts["insurer_paid"] = paid
    return amounts, codes


def _claim_number(eob: dict) -> str:
    ids = eob.get("identifier") or []
    for i in ids:  # CARIN: the payer's unique claim id has type "uc"
        if any(c.get("code") == "uc" for c in (i.get("type") or {}).get("coding") or []) and i.get("value"):
            return str(i["value"])
    return str(ids[0]["value"]) if ids and ids[0].get("value") else eob.get("id", "")


def _provider_name(eob: dict) -> str:
    ref = (eob.get("provider") or {})
    if ref.get("display"):
        return ref["display"]
    if (r := ref.get("reference") or "").startswith("#"):
        for c in eob.get("contained") or []:
            if c.get("id") == r[1:] and c.get("name"):
                return c["name"] if isinstance(c["name"], str) else " ".join(
                    filter(None, [*(c["name"][0].get("given") or []), c["name"][0].get("family")]))
    return "Unknown provider"


def _network(eob: dict) -> str:
    for s in eob.get("supportingInfo") or []:
        for c in (s.get("code") or {}).get("coding") or []:
            code = (c.get("code") or "").lower()
            if code in ("innetwork", "in-network"):
                return "in_network"
            if code in ("outofnetwork", "out-of-network"):
                return "out_of_network"
    return "unknown"


@dataclass
class Mapped:
    claim_number: str
    provider: str
    service_date: str
    processed: str
    status: str
    network: str
    amounts: dict[str, int]
    lines: list[dict] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)


def map_eob(eob: dict) -> Mapped | None:
    """One ExplanationOfBenefit as an MHS claim in cents; None when it has no service date or no amounts."""
    period = eob.get("billablePeriod") or {}
    lines, item_amounts, item_codes = [], [], []
    for item in eob.get("item") or []:
        amounts, codes = _categories(item.get("adjudication"))
        when = item.get("servicedDate") or (item.get("servicedPeriod") or {}).get("start") or period.get("start")
        code = next((c.get("code") for c in (item.get("productOrService") or {}).get("coding") or [] if c.get("code")),
                    None)
        line = {k: v for k, v in amounts.items()}
        if when:
            line["service_date"] = str(when)[:10]
        if code:
            line["code"] = str(code)
        if codes:
            line["remark_codes"] = codes
        lines.append(line)
        item_amounts.append(amounts)
        item_codes += codes
    totals, claim_codes = _categories(eob.get("total") or [])
    for name in MONEY_FIELDS:  # a total the payer left out is the sum of its items
        if name not in totals and any(name in a for a in item_amounts):
            totals[name] = sum(a.get(name, 0) for a in item_amounts)
    if "billed" not in totals:
        return None
    if "patient_responsibility" not in totals:
        totals["patient_responsibility"] = sum(totals.get(k, 0) for k in ("deductible", "copay", "coinsurance",
                                                                           "not_covered"))
    totals.setdefault("insurer_paid", 0)
    totals.setdefault("allowed", totals["billed"] - totals.get("adjustment", 0))
    if "adjustment" not in totals:
        totals["adjustment"] = totals["billed"] - totals["allowed"]
    when = str(period.get("start") or (lines[0].get("service_date") if lines else "") or "")[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", when):
        return None
    denied = eob.get("outcome") == "error" or (totals["insurer_paid"] == 0 and totals.get("not_covered", 0)
                                                 >= totals["allowed"] > 0)
    return Mapped(_claim_number(eob), _provider_name(eob), when, str(eob.get("created") or when)[:10],
                  "denied" if denied else "processed", _network(eob), totals, lines, list(dict.fromkeys(claim_codes)))


def _norm(claim: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", claim.upper())


@dataclass
class Result:
    ingest: dict
    read: int = 0
    already: int = 0  # the same claim and amounts already on file (TC-ING-09-3)
    versions: int = 0
    skipped: list[str] = field(default_factory=list)


def to_ingest(eobs: list[dict], payer: Payer, member_id: str | None, providers: list[dict], visits: list[dict],
              documents: list[dict], plans: list[dict]) -> Result:
    """An ingest file (dollars) with the pulled claims, their providers and visits. A claim already on file with the
    same amounts is left out; with different amounts it becomes a newer version (MAT-08)."""
    resolver = Providers(providers)
    existing = {}
    for d in documents:
        if d.get("type") == "eob" and d.get("claim_number"):
            existing.setdefault(_norm(d["claim_number"]), []).append(d)
    known_visits = list(visits)
    out = {"schema_version": "0.1", "source": {"prepared_by": f"MHS insurer connection: {payer.label}"},
           "visits": [], "documents": []}
    res = Result(out)
    for raw in eobs:
        m = map_eob(raw)
        if m is None:
            res.skipped.append("A claim without a service date or amounts was left out.")
            continue
        res.read += 1
        year = int(m.service_date[:4])
        plan = next((p for p in plans if p.get("plan_year") == year
                     and p.get("coverage_order") in (None, "primary")
                     and (not member_id or not p.get("member_ids") or member_id in p["member_ids"])), None)
        if plan is None:
            res.skipped.append(f"Claim {m.claim_number} ({m.service_date}) was left out: add your {year} plan in "
                               "Settings, then connect again.")
            continue
        pid = resolver.resolve(m.provider)
        same = sorted(existing.get(_norm(m.claim_number), []), key=lambda d: (d["date"], d["id"]))
        if same and all(same[-1].get(k) == m.amounts.get(k) for k in ("billed", "insurer_paid",
                                                                       "patient_responsibility")):
            res.already += 1
            continue
        visit = next((v for v in known_visits if v["provider_id"] == pid and v["date"] == m.service_date
                      and (not member_id or v.get("member_id") in (None, member_id))), None)
        if same:
            visit = next((v for v in known_visits if v["id"] == same[-1]["visit_id"]), visit)
        if visit is None:
            vid = base = f"v-{m.service_date}-{pid.removeprefix('prov-')}"
            n = 2
            while any(v["id"] == vid for v in known_visits):
                vid, n = f"{base}-{n}", n + 1
            visit = {"id": vid, "date": m.service_date, "provider_id": pid, "category": "provider_visit",
                     "plan_id": plan["id"], "description": f"From {payer.label}",
                     "extensions": {"feed": "fhir"}}
            if member_id:
                visit["member_id"] = member_id
            known_visits.append(visit)
            out["visits"].append(visit)
        doc_id = f"eob-{re.sub(r'[^a-z0-9]+', '-', m.claim_number.lower()).strip('-') or raw.get('id', 'x')}"
        doc = {"id": doc_id, "type": "eob", "date": m.processed, "plan_id": plan["id"], "provider_id": pid,
               "visit_id": visit["id"], "claim_number": m.claim_number, "claim_status": m.status,
               "network_status": m.network, "extensions": {"feed": "fhir", "payer": payer.name},
               **{k: dollars(v) for k, v in m.amounts.items()}}
        if same:
            n = 2
            ids = {d["id"] for d in documents}
            while f"{same[0]['id']}-v{n}" in ids:
                n += 1
            doc.update(id=f"{same[0]['id']}-v{n}", version_of=same[-1]["id"], version_reason="reprocessed")
            res.versions += 1
        if m.codes:
            doc["remark_codes"] = m.codes
        if m.lines:
            doc["lines"] = [{k: (dollars(v) if k in MONEY_FIELDS else v) for k, v in l.items()} for l in m.lines]
        out["documents"].append(doc)
    if resolver.new:
        out["providers"] = list(resolver.new.values())
    for key in ("visits", "documents"):
        if not out[key]:
            del out[key]
    return res
