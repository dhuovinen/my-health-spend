"""False-positive rate of findings (PLT-02, TC-PLT-02-2; test plan A-01; ADR-044).

A finding the member closed as wrong is a false positive. The rate is wrong ÷ (real + wrong) over the findings closed
in a period, per finding kind and overall; findings still open and closings without a verdict are counted beside it,
not in it. Counts only: nothing here carries a reason, a name, a date of service or an amount.
Pure functions; no database or web imports.
"""

from dataclasses import dataclass, field

from mhs.core.reconcile import CHECK_NAMES, FINDING_KINDS, Check, Report

TARGET = 0.05  # at most 5% of findings dismissed as wrong (A-01)
# A balance owed and a missing claim aren't errors the member can call wrong (they close only with a dispute), so
# they are neither offered for a verdict nor counted.
NOT_CLOSABLE = {"C6", "claim_filed"}


@dataclass
class KindCounts:
    key: str  # a finding kind (missed_adjustment) or, for a check without kinds, its code (C3)
    real: int = 0
    wrong: int = 0
    unrated: int = 0  # closed before the member was asked
    open: int = 0

    @property
    def label(self) -> str:
        return FINDING_KINDS.get(self.key) or CHECK_NAMES.get(self.key, self.key)

    @property
    def decided(self) -> int:
        return self.real + self.wrong

    @property
    def rate(self) -> float | None:
        return self.wrong / self.decided if self.decided else None

    @property
    def meets_target(self) -> bool | None:
        return None if self.rate is None else self.rate <= TARGET

    def add(self, other: "KindCounts") -> None:
        self.real, self.wrong = self.real + other.real, self.wrong + other.wrong
        self.unrated, self.open = self.unrated + other.unrated, self.open + other.open


@dataclass
class Accuracy:
    kinds: dict[str, KindCounts] = field(default_factory=dict)
    releases: dict[str, int] = field(default_factory=dict)  # release label -> decided findings

    def counts(self, key: str) -> KindCounts:
        return self.kinds.setdefault(key, KindCounts(key))

    @property
    def rows(self) -> list[KindCounts]:
        return sorted(self.kinds.values(), key=lambda k: (-k.decided, -k.open, k.label))

    @property
    def total(self) -> KindCounts:
        out = KindCounts("all")
        for k in self.kinds.values():
            out.add(k)
        return out

    def __add__(self, other: "Accuracy") -> "Accuracy":
        out = Accuracy()
        for acc in (self, other):
            for key, k in acc.kinds.items():
                out.counts(key).add(k)
            for release, n in acc.releases.items():
                out.releases[release] = out.releases.get(release, 0) + n
        return out


def finding_key(code: str, kind: str = "") -> str:
    return kind or code


def open_findings(reports: list[Report]) -> list[Check]:
    """The findings a member could still close, over reports for different years (each visit is in one)."""
    return [c for r in reports for v in r.visits for c in v.findings if c.code not in NOT_CLOSABLE]


def accuracy(visits: list[dict], open_now: list[Check] = (), start: str | None = None, end: str | None = None,
             release: str | None = None) -> Accuracy:
    """Count the member's verdicts on the findings closed from start to end (ISO dates, both included; None is
    open-ended), for one release or all, and the findings open now beside them."""
    out = Accuracy()
    for visit in visits:
        for f in visit.get("closed_findings") or []:
            closed = f.get("closed") or ""
            if (start and closed < start) or (end and closed > end):
                continue
            if (release and f.get("release") != release) or f["code"] in NOT_CLOSABLE:
                continue
            counts = out.counts(finding_key(f["code"], f.get("kind", "")))
            verdict = f.get("verdict")
            if verdict == "real":
                counts.real += 1
            elif verdict == "wrong":
                counts.wrong += 1
            else:
                counts.unrated += 1
                continue
            label = f.get("release") or "unknown"
            out.releases[label] = out.releases.get(label, 0) + 1
    for c in open_now:
        out.counts(finding_key(c.code, c.kind)).open += 1
    return out


def percent(rate: float | None) -> str:
    return "–" if rate is None else f"{rate * 100:.1f}%"
