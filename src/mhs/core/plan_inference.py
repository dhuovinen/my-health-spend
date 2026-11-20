"""The plan's in-network terms as the household's own EOBs show them (REC-15, ADR-056).

Each adjudicated EOB shows how the insurer applied the plan: the allowed amount, then the deductible, copay and
coinsurance it charged. Read in the insurer's processing order, a plan year's EOBs show the coinsurance rate, the copay
per service type, whether copays wait for the deductible, and, once reached, the deductible and out-of-pocket maximum.
Every term says how sure it is (known, at least, conflicting or unknown) and which claims it rests on; claims that
don't fit a known term are outliers. Nothing is stored: it is worked out again with the report.

Pure functions over record dicts, money in integer cents. No database or web imports.
"""

from collections import Counter
from dataclasses import dataclass, field

from mhs.core.costshare import SERVICE_TYPES, SHARE_KEYS, Terms, claim_order, terms_of
from mhs.core.lines import TOLERANCE, fmt

MIN_AGREE = 3  # claims that must agree before a term is known
AGREE_SHARE = 0.8  # ... and the share of the claims showing the term that must agree

KNOWN, AT_LEAST, CONFLICTING, UNKNOWN = "known", "at_least", "conflicting", "unknown"
LIMITS = {
    "deductible": "Deductible (each person)",
    "family_deductible": "Deductible (family)",
    "oop": "Out-of-pocket maximum (each person)",
    "family_oop": "Out-of-pocket maximum (family)",
}


@dataclass
class Inferred:
    key: str  # coinsurance | copay:<service type> | copays_after_deductible | deductible | family_deductible | oop ...
    state: str = UNKNOWN
    value: float | int | bool | None = None  # rate as a fraction, money in cents, or yes/no
    claims: list[str] = field(default_factory=list)  # claim ids that agree with the value
    outliers: list[tuple[str, str]] = field(default_factory=list)  # (claim id, what it shows)
    shown: int = 0  # claims that show this term at all
    anchor: str = ""  # the claim at which the term became known

    @property
    def label(self) -> str:
        if self.key == "coinsurance":
            return "Coinsurance"
        if self.key.startswith("copay:"):
            kind = self.key.split(":", 1)[1]
            return f"{SERVICE_TYPES.get(kind, kind.replace('_', ' ').capitalize())} copay"
        if self.key == "copays_after_deductible":
            return "Copays wait for the deductible"
        return LIMITS[self.key]

    @property
    def text(self) -> str:
        if self.value is None:
            return "No single answer" if self.state == CONFLICTING else "Not shown yet"
        if self.key == "coinsurance":
            shown = f"{self.value * 100:.1f}".removesuffix(".0") + "%"
        elif isinstance(self.value, bool):
            shown = "Yes" if self.value else "No"
        else:
            shown = fmt(self.value)
        return f"at least {shown}" if self.state == AT_LEAST else shown

    @property
    def usable(self) -> bool:
        """Only a known term is ever used to work anything out."""
        return self.state == KNOWN and self.value is not None


@dataclass
class InferredTerms:
    plan_id: str
    fields: dict[str, Inferred] = field(default_factory=dict)

    def get(self, key: str) -> Inferred:
        return self.fields.get(key) or Inferred(key)

    @property
    def rows(self) -> list[Inferred]:
        """For display: the terms the EOBs say something about, in plan-document order."""
        order = ["coinsurance", *sorted(k for k in self.fields if k.startswith("copay:")), "copays_after_deductible",
                 *LIMITS]
        return [self.fields[k] for k in order if k in self.fields and self.fields[k].state != UNKNOWN]


# ---------- reading the claims ----------

def _usable(c: dict) -> bool:
    return (c.get("claim_status") != "denied" and c.get("network_status") != "out_of_network"
            and c.get("allowed") is not None and any(c.get(k) is not None for k in SHARE_KEYS))


def _share(c: dict) -> int:
    return sum(c.get(k) or 0 for k in SHARE_KEYS)


def _decide(votes: list[tuple[object, list[str]]], shown: int, close) -> tuple[str, object, list[str], list[str]]:
    """The value most claims agree with, and whether enough do. votes: (value, claim ids that show it)."""
    if not votes or shown < MIN_AGREE:
        return UNKNOWN, None, [], []  # too few claims to say anything (TC-REC-15-4)
    best_value, best = None, []
    for value, _ in votes:
        agree = [cid for v, ids in votes if close(v, value) for cid in ids]
        if len(agree) > len(best):
            best_value, best = value, agree
    others = [cid for v, ids in votes if not close(v, best_value) for cid in ids]
    known = len(best) >= MIN_AGREE and len(best) >= AGREE_SHARE * max(shown, 1)
    return (KNOWN if known else CONFLICTING), best_value, best, others


def _money_close(a, b) -> bool:
    return abs(a - b) < TOLERANCE


def _rate(rows: list[tuple[dict, dict]], skip: set[str]) -> Inferred:
    out = Inferred("coinsurance")
    seen = []  # (claim, base)
    for c, _ in rows:
        base = c["allowed"] - (c.get("deductible") or 0) - (c.get("copay") or 0)
        if (c.get("coinsurance") or 0) > 0 and base > 0 and c["id"] not in skip:
            seen.append((c, base))
    out.shown = len(seen)
    if len(seen) < MIN_AGREE:
        return out
    candidates = Counter(round(c["coinsurance"] / base * 200) / 200 for c, base in seen)  # to the nearest 0.5%
    best_rate, best = None, []
    for rate, _ in candidates.most_common():
        agree = [c["id"] for c, base in seen if abs(round(base * rate) - c["coinsurance"]) < TOLERANCE]
        if len(agree) > len(best):
            best_rate, best = rate, agree
    out.value, out.claims = best_rate, best
    out.state = KNOWN if len(best) >= MIN_AGREE and len(best) >= AGREE_SHARE * len(seen) else CONFLICTING
    out.outliers = [(c["id"], f"{c['coinsurance'] / base * 100:.1f}% of {fmt(base)}") for c, base in seen
                    if c["id"] not in best]
    if out.state == KNOWN:
        out.anchor = best[MIN_AGREE - 1]
    return out


def _copays(rows: list[tuple[dict, dict]], skip: set[str]) -> dict[str, Inferred]:
    by_type: dict[str, list[dict]] = {}
    for c, v in rows:
        kind = v.get("service_type")
        if kind and kind != "preventive" and (c.get("copay") or 0) > 0 and c["id"] not in skip:
            by_type.setdefault(kind, []).append(c)
    out = {}
    for kind, cs in by_type.items():
        f = Inferred(f"copay:{kind}", shown=len(cs))
        votes = [(amount, [c["id"] for c in cs if c["copay"] == amount]) for amount in dict.fromkeys(c["copay"] for c in cs)]
        f.state, f.value, f.claims, others = _decide(votes, len(cs), _money_close)
        f.outliers = [(c["id"], f"copay {fmt(c['copay'])}") for c in cs if c["id"] in others]
        if f.state == KNOWN:
            f.anchor = [c["id"] for c in cs if c["id"] in f.claims][MIN_AGREE - 1]
        out[f.key] = f
    return out


def _copays_after_deductible(rows: list[tuple[dict, dict]]) -> Inferred:
    """For the service types the EOBs charge a copay for: yes when a claim of that type is charged deductible instead
    (the copay waited); no when it is charged a copay with no deductible while the same person is still charged
    deductible on a later claim."""
    f = Inferred("copays_after_deductible")
    copay_types = {v.get("service_type") for c, v in rows if (c.get("copay") or 0) > 0} - {None, "preventive"}
    yes, no = [], []
    for i, (c, v) in enumerate(rows):
        if v.get("service_type") not in copay_types:
            continue
        if (c.get("deductible") or 0) > 0:
            yes.append(c["id"])
        elif (c.get("copay") or 0) > 0 and any((later.get("deductible") or 0) > 0
                                               and lv.get("member_id") == v.get("member_id")
                                               for later, lv in rows[i + 1:]):
            no.append(c["id"])
    f.shown = len(yes) + len(no)
    votes = [(True, yes)] * bool(yes) + [(False, no)] * bool(no)
    f.state, f.value, f.claims, others = _decide(votes, f.shown, lambda a, b: a == b)
    f.outliers = [(cid, "deductible before the copay" if cid in yes else "copay before the deductible")
                  for cid in others]
    if f.state == KNOWN:
        f.anchor = f.claims[MIN_AGREE - 1]
    return f


def _limits(rows: list[tuple[dict, dict]], amount_of, after, mid, individual: str, family: str
            ) -> dict[str, Inferred]:
    """A deductible or out-of-pocket maximum, from where the EOBs stop charging it.

    Every claim that charges it could be where it ran out: one that ran out partway through the claim (`mid`), or one
    whose person's next claim shows it had (`after`). Each such end point is supported by itself and the person's later
    claims that show it had run out, and contradicted by the person's later claims that still charge it and by earlier
    end points. The end point with the most support wins; a tie is no answer (an insurer mistake on either side would
    look the same). It ran out at the person's own amount unless other people's claims made up part of the family total
    and nobody is charged it again afterwards: then it was the family amount."""
    running: dict[str, int] = {}
    fam = 0
    totals: list[tuple[int, int]] = []  # (person's running total, family running total) after each claim
    for c, v in rows:
        m = v.get("member_id") or ""
        running[m] = running.get(m, 0) + amount_of(c)
        fam += amount_of(c)
        totals.append((running[m], fam))
    ind_votes, fam_votes, contra = [], [], {}
    for m in dict.fromkeys(v.get("member_id") or "" for _, v in rows):
        mine = [i for i, (_, v) in enumerate(rows) if (v.get("member_id") or "") == m]
        charged = [i for i in mine if amount_of(rows[i][0]) > 0]
        ends = []
        for i in charged:
            nxt = next((k for k in mine if k > i and (amount_of(rows[k][0]) > 0 or after(*rows[k]))), None)
            if mid(rows[i][0]) or (nxt is not None and amount_of(rows[nxt][0]) == 0):
                ends.append(i)
        scored = []
        for i in ends:
            support = [rows[i][0]["id"]] + [rows[k][0]["id"] for k in mine if k > i and after(*rows[k])]
            if len(support) <= sum(1 for k in charged if k > i):
                continue  # charged again more often than not: it hadn't run out (a fully covered service, say)
            scored.append((len(support), i, support, None))
        ends = [i for _, i, _, _ in scored]
        scored = [(n, i, support, [k for k in charged if k > i] + [k for k in ends if k < i])
                  for n, i, support, _ in scored]
        if not scored:
            continue
        scored.sort(key=lambda x: (-x[0], x[1]))
        top, i, support, against = scored[0]
        if len(scored) > 1 and scored[1][0] == top:
            for _, k, sup, _ in scored:  # a tie: every end point is a claim that doesn't fit
                contra[rows[k][0]["id"]] = f"{fmt(totals[k][0])} reached"
            ind_votes.append((None, []))
            continue
        for k in against:
            contra[rows[k][0]["id"]] = (f"still charged {fmt(amount_of(rows[k][0]))}" if k > i
                                        else f"stopped at {fmt(totals[k][0])}")
        own, total = totals[i]
        others_charged_after = any(amount_of(c) > 0 for c, v in rows[i + 1:] if (v.get("member_id") or "") != m)
        if total > own and not others_charged_after:
            support += [c["id"] for c, v in rows[i + 1:] if (v.get("member_id") or "") != m and after(c, v)]
            fam_votes.append((total, support))
        else:
            ind_votes.append((own, support))
    out = {}
    for key, votes, floor in ((individual, ind_votes, max(running.values(), default=0)), (family, fam_votes, fam)):
        f = Inferred(key)
        tied = any(value is None for value, _ in votes)
        votes = [(value, ids) for value, ids in votes if value is not None]
        own_contra = contra if key == individual else {}  # a person's contradicting claims count against their amount
        f.shown = sum(len(ids) for _, ids in votes) + len(own_contra)
        f.state, f.value, f.claims, others = _decide(votes, f.shown, _money_close)
        f.outliers = list(own_contra.items()) + [(cid, "a different amount reached") for cid in others]
        if f.state == KNOWN:
            f.anchor = next(ids[0] for value, ids in votes if _money_close(value, f.value))
        elif tied or f.state == CONFLICTING:
            f.state, f.value = CONFLICTING, None
        elif floor > 0:
            f.state, f.value = AT_LEAST, floor
        out[key] = f
    return out


def infer(claims: list[dict], visits: dict[str, dict], plan_id: str, without: str = "") -> InferredTerms:
    """One plan's terms from its claims (primary, current versions, as the report holds them), leaving out `without`
    when a claim is checked against terms it mustn't have helped set."""
    rows = [(c, visits.get(c["visit_id"], {})) for c in sorted(claims, key=claim_order)
            if c.get("plan_id") == plan_id and c["id"] != without and _usable(c)]
    out = InferredTerms(plan_id)
    if not rows:
        return out

    def ded_after(c, v):  # the deductible would have applied, and wasn't charged
        return (c["allowed"] > 0 and not c.get("deductible") and v.get("service_type") != "preventive"
                and ((c.get("coinsurance") or 0) > 0 or not c.get("copay")))

    def oop_after(c, v):  # the member would have paid something, and paid nothing
        return c["allowed"] > 0 and _share(c) == 0 and v.get("service_type") != "preventive"

    def ded_mid(c):  # the deductible ran out partway: some of the allowed amount went to a copay, coinsurance or the plan
        return 0 < (c.get("deductible") or 0) < c["allowed"]

    oop = _limits(rows, _share, oop_after, lambda c: False, "oop", "family_oop")
    capped = {f.anchor for f in oop.values() if f.anchor}  # the claim that hit the cap shows a reduced share
    out.fields["coinsurance"] = _rate(rows, capped)
    out.fields.update(_copays(rows, capped))
    out.fields["copays_after_deductible"] = _copays_after_deductible(rows)
    out.fields.update(_limits(rows, lambda c: c.get("deductible") or 0, ded_after, ded_mid, "deductible",
                              "family_deductible"))
    out.fields.update(oop)
    return out


def infer_all(claims: list[dict], visits: dict[str, dict], plans: dict[str, dict]) -> dict[str, InferredTerms]:
    return {pid: infer(claims, visits, pid) for pid in plans}


# ---------- using it ----------

def fill(t: Terms, inferred: InferredTerms, service_type: str | None) -> tuple[Terms, list[str]]:
    """The entered terms with each empty one filled by a known inferred term, and what was filled ("coinsurance 20%").
    An entered term always wins; a filled term never counts as confirmed."""
    used: list[str] = []
    out = Terms(t.deductible, t.family_deductible, t.oop, t.family_oop, t.rate, dict(t.copays), t.hdhp, t.confirmed)
    if out.rate is None and (f := inferred.get("coinsurance")).usable:
        out.rate = f.value
        used.append(f"coinsurance {f.text}")
    if service_type and service_type not in out.copays and (f := inferred.get(f"copay:{service_type}")).usable:
        out.copays[service_type] = f.value
        used.append(f"{f.label.lower()} {f.text}")
    for key in LIMITS:
        if getattr(out, key) is None and (f := inferred.get(key)).usable:
            setattr(out, key, f.value)
            used.append(f"{f.label.lower()} {f.text}")
    if used:
        out.confirmed = False
    return out, used


@dataclass
class Mismatch:
    key: str
    entered: str
    inferred: Inferred
    amount: int  # cents apart for money terms; 0 for the rate
    detail: str


def mismatches(plan: dict, inferred: InferredTerms) -> list[Mismatch]:
    """Entered terms that differ from known inferred ones by more than the tolerance (TC-REC-15-6)."""
    t = terms_of(plan)
    out = []
    pairs = [("coinsurance", t.rate)] + [(f"copay:{k}", v) for k, v in t.copays.items()] + \
            [(key, getattr(t, key)) for key in LIMITS]
    for key, entered in pairs:
        f = inferred.get(key)
        if entered is None or not f.usable:
            continue
        if key == "coinsurance":
            if abs(entered - f.value) < 0.005:
                continue
            entered_text, amount = f"{entered * 100:.1f}".removesuffix(".0") + "%", 0
        else:
            if abs(entered - f.value) < TOLERANCE:
                continue
            entered_text, amount = fmt(entered), abs(entered - f.value)
        n = len(f.claims)
        detail = (f"{n} EOBs under this plan show a {f.label.lower()} of {f.text}, but your plan entry says "
                  f"{entered_text}. Either the plan entry or the insurer is wrong: check your plan documents, then "
                  f"correct the entry on Coverage or ask the insurer to reprocess the claims")
        out.append(Mismatch(key, entered_text, f, amount, detail))
    return out
