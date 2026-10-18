"""HSA and tax (Release 2: TAX-01 to TAX-04, TAX-06 to TAX-10; ADR-006, ADR-010, ADR-021, ADR-042).

Pure functions over plain record dicts and the engine's Reports (money in integer cents). The IRS limits and the
Publication 502 categories are data passed in (PLT-01), never constants here. Everything is a possibility, not an
eligibility ruling (CMP-04): tags say "likely", and the pages print DISCLAIMER beside every suggestion.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from mhs.core.lines import fmt
from mhs.core.reconcile import Allocation, Dataset, Report, VisitResult

DISCLAIMER = ("Information, not legal, tax or medical advice. Tags and suggestions are possibilities based on IRS "
              "Publication 502 and what you entered here; check with a tax professional or your plan administrator "
              "before you act on them.")
TAGS = {"likely_qualified": "Likely qualified", "likely_not_qualified": "Likely not qualified",
        "needs_documentation": "Needs documentation"}
SPENDING = ("fsa", "lpfsa", "hra")  # spending accounts with a plan year
TAX_ADVANTAGED = ("hsa", *SPENDING)
ACCOUNT_LABELS = {"hsa": "HSA", "fsa": "Health FSA", "lpfsa": "Limited-purpose FSA", "hra": "HRA"}
STRATEGIES = {"pay_now": "Pay from the HSA now", "save_for_later": "Save the HSA for later"}
FORFEIT_WINDOW_DAYS = 90  # an FSA balance this close to its last day counts as about to be forfeited (TAX-03)
FSA_CHILD_AGE_LIMIT = 27  # FSAs and HRAs may pay for a child who hasn't turned 27 by the end of the year
CATCH_UP_AGE = 55
UNMATCHED = "unmatched"  # year-end summary row for HSA money not matched to a visit
NOBODY = ""
MISTAKE_GUIDANCE = (
    "If this HSA payment was a genuine mistake, you can ask your HSA custodian to take the money back as a mistaken "
    "distribution. Custodians usually need it by April 15 of the year after you knew, or should have known, it was "
    "a mistake (IRS Notice 2004-50), and not every custodian accepts returns. Returned in time, it isn't taxed. If it "
    "stays in your hands, it's usually taxable income, plus an extra 20% tax before age 65.")
LAST_MONTH_WARNING = (
    "The last-month rule needs you to stay HSA-eligible for the whole testing period, through December 31, {next}. "
    "If you don't, the amount above the monthly limit becomes taxable income plus a 10% additional tax.")


# ---------- reference tables (PLT-01) ----------

@dataclass(frozen=True)
class Category:
    id: str
    cite: str  # the IRS Publication 502 heading
    name: str
    tag: str
    scope: str = "medical"  # medical | dental | vision
    words: tuple[str, ...] = ()
    provider_kinds: tuple[str, ...] = ()
    visit_categories: tuple[str, ...] = ()
    documentation: str = ""  # what would make it count
    note: str = ""


@dataclass(frozen=True)
class CategoryTable:
    version: str
    effective_from: str
    source: str
    categories: tuple[Category, ...]

    def get(self, category_id: str) -> Category | None:
        return next((c for c in self.categories if c.id == category_id), None)


@dataclass(frozen=True)
class YearLimits:
    year: int
    hsa_self_only: int
    hsa_family: int
    hsa_catch_up: int
    fsa: int
    fsa_carryover: int
    source: str = ""


@dataclass
class TaxTables:
    categories: list[CategoryTable]  # oldest effective date first
    limits: dict[int, YearLimits]

    def categories_on(self, day: str) -> CategoryTable:
        """The category table in effect on a date (the oldest one for earlier dates)."""
        current = self.categories[0]
        for t in self.categories:
            if t.effective_from <= day:
                current = t
        return current

    def version(self, version: str) -> CategoryTable | None:
        return next((t for t in self.categories if t.version == version), None)


# ---------- tags (TAX-01, ADR-021) ----------

@dataclass
class Tag:
    tag: str  # likely_qualified | likely_not_qualified | needs_documentation
    category: Category
    version: str
    source: str  # member | words | provider | category | default
    documented: bool = False  # a letter of medical necessity is on file

    @property
    def qualified(self) -> bool:
        """Counts as a qualified expense for the vault, recommendations and the summary (still a possibility)."""
        return self.tag == "likely_qualified" or (self.tag == "needs_documentation" and self.documented)

    @property
    def needs_letter(self) -> bool:
        return self.tag == "needs_documentation" and not self.documented

    @property
    def label(self) -> str:
        return TAGS[self.tag] + (" (letter on file)" if self.documented else "")

    @property
    def cite(self) -> str:
        return f'IRS Publication 502, "{self.category.cite}"'


def _words_match(words: tuple[str, ...], text: str) -> bool:
    return any(re.search(r"\b" + re.escape(w), text) for w in words)


def tag_visit(visit: dict, provider: dict | None, receipts: list[dict], tables: TaxTables) -> Tag:
    """TAX-01: the member's category first, then words in the description or receipt items, then the provider's kind,
    then the visit's category. Tagged with the table in effect on the visit date, or the version the member's choice
    was made with, so a new table never retags earlier expenses (TC-TAX-01-4)."""
    choice = visit.get("tax") or {}
    table = (tables.version(choice["version"]) if choice.get("version") else None) or tables.categories_on(visit["date"])
    documented = bool(choice.get("documentation"))
    category, source = None, "default"
    if choice.get("category"):
        category, source = table.get(choice["category"]), "member"
    if category is None:
        text = " ".join([visit.get("description") or "",
                         *(i.get("description") or "" for r in receipts for i in r.get("items") or [])]).lower()
        category = next((c for c in table.categories if c.words and _words_match(c.words, text)), None)
        source = "words"
    if category is None and provider:
        category = next((c for c in table.categories if provider.get("kind") in c.provider_kinds), None)
        source = "provider"
    if category is None:
        category = next((c for c in table.categories if visit.get("category") in c.visit_categories), None)
        source = "category"
    if category is None:
        category, source = table.get("other") or table.categories[-1], "default"
    tag = category.tag
    if tag == "likely_not_qualified" and documented and category.documentation:
        tag = "needs_documentation"  # supplements a practitioner recommends (TC-TAX-01-2)
    return Tag(tag, category, table.version, source, documented=documented and tag == "needs_documentation")


# ---------- account rules (TAX-02) ----------

def _day(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def plan_period(account: dict) -> tuple[date, date] | None:
    """A spending account's plan year (default: the calendar `plan_year`), or None when it has none set."""
    year = account.get("plan_year")
    start = account.get("plan_year_start") or (f"{year}-01-01" if year else None)
    end = account.get("plan_year_end") or (f"{year}-12-31" if year else None)
    return (_day(start), _day(end)) if start and end else None


def last_expense_day(account: dict) -> date | None:
    """The last day a plan year's money pays expenses: the plan year end, or with a grace period the 15th of the
    third month after it (the IRS two and a half months)."""
    period = plan_period(account)
    if not period:
        return None
    end = period[1]
    if not account.get("grace_period"):
        return end
    month = end.month + 3
    return date(end.year + (month - 1) // 12, (month - 1) % 12 + 1, 15)


def funds_usable(account: dict, day: str | date) -> bool:
    """TC-TAX-02-1: the plan year's money pays an expense incurred from the start through the last expense day."""
    period = plan_period(account)
    if not period:
        return True
    return period[0] <= _day(day) <= last_expense_day(account)


def carryover(account: dict, unspent: int, tables: TaxTables) -> tuple[int, int]:
    """TC-TAX-02-2: (carried into the next plan year, forfeited) for money unspent after the last expense day. The
    plan's carryover is capped by the year's IRS maximum; a plan with a grace period carries nothing over."""
    if unspent <= 0 or account.get("grace_period"):
        return 0, max(unspent, 0)
    cap = account.get("carryover") or 0
    limits = tables.limits.get(account.get("plan_year") or 0)
    if limits:
        cap = min(cap, limits.fsa_carryover)
    carried = min(unspent, cap)
    return carried, unspent - carried


def claim_on_time(account: dict, filed: str | date) -> bool:
    """TC-TAX-02-3: a claim filed after the run-out deadline is past it."""
    deadline = account.get("run_out_end")
    return not deadline or _day(filed) <= _day(deadline)


def covers(account: dict, tag: Tag) -> tuple[bool, str]:
    """Whether an account's rules let it pay this kind of expense (TC-TAX-02-4, TC-TAX-02-5)."""
    kind = account.get("type")
    if kind not in TAX_ADVANTAGED:
        return False, "Not a tax-advantaged account"
    if tag.tag == "likely_not_qualified":
        return False, "Likely not a qualified expense"
    if kind == "lpfsa" and tag.category.scope not in ("dental", "vision"):
        return False, "A limited-purpose FSA pays only dental and vision care"
    if kind == "hra" and account.get("eligible_categories") and tag.category.id not in account["eligible_categories"]:
        return False, "Not on this HRA's list of eligible expenses"
    return True, ""


def account_balance(account: dict, documents: list[dict]) -> tuple[int | None, str]:
    """The newest known balance: the account's own `balance`, or a newer running balance from an export."""
    best = (account.get("balance_as_of") or "", account.get("balance"))
    for d in documents:
        if d.get("account_id") == account["id"] and d.get("account_balance_after") is not None and d["date"] > best[0]:
            best = (d["date"], d["account_balance_after"])
    return best[1], best[0]


@dataclass
class Forfeit:
    account: dict
    amount: int  # balance above the carryover
    days: int  # until the last expense day
    last_day: date


def at_risk(account: dict, documents: list[dict], today: date, tables: TaxTables) -> Forfeit | None:
    """Spending-account money that would be forfeited soon: the balance above the carryover, with
    FORFEIT_WINDOW_DAYS or fewer left before the last expense day."""
    last = last_expense_day(account)
    balance, _ = account_balance(account, documents)
    if account.get("type") not in SPENDING or not last or not balance or balance <= 0:
        return None
    days = (last - today).days
    _, forfeited = carryover(account, balance, tables)
    if 0 <= days <= FORFEIT_WINDOW_DAYS and forfeited > 0:
        return Forfeit(account, forfeited, days, last)
    return None


# ---------- who each account may pay for (TAX-09) ----------

def holder_of(account: dict, members: list[dict]) -> dict | None:
    ids = account.get("member_ids") or []
    by_id = {m["id"]: m for m in members}
    if ids and ids[0] in by_id:
        return by_id[ids[0]]
    return next((m for m in members if m.get("relationship") == "self"), None)


def may_pay_for(account: dict, member: dict | None, year: int) -> tuple[str, str]:
    """("yes" | "no" | "check", why). An HSA pays for the holder, a spouse and the year's tax dependents; a health
    FSA, LPFSA or HRA also for a child under 27 at the end of the year. Unknown status is "check", never a flag."""
    if member is None:
        return "check", "The visit isn't assigned to a household member."
    name = member["name"]
    relationship = member.get("relationship")
    if relationship in ("self", "spouse"):
        return "yes", "You or your spouse"
    dependent = (member.get("tax_dependent") or {}).get(str(year))
    if dependent is True:
        return "yes", f"{name} is your tax dependent in {year}"
    if account.get("type") != "hsa" and relationship == "child" and member.get("birth_year"):
        if year - member["birth_year"] < FSA_CHILD_AGE_LIMIT:
            return "yes", f"{name} is under 27 at the end of {year}"
    if dependent is False:
        who = ("an HSA pays only for you, your spouse and your tax dependents" if account.get("type") == "hsa"
               else "this account pays only for you, your spouse, your tax dependents and children under 27")
        return "no", f"{name} isn't your tax dependent in {year}; {who}."
    return "check", f"Is {name} your tax dependent in {year}? Set it under People."


# ---------- recommendation (TAX-03, ADR-010) ----------

@dataclass
class Recommendation:
    action: str  # hsa | vault | account | other
    text: str
    account: dict | None = None
    alternative: str = ""
    letter: str = ""  # documentation to get first


def recommend(tag: Tag, member: dict | None, visit_date: str, accounts: list[dict], documents: list[dict],
              strategy: str, today: date, tables: TaxTables) -> Recommendation:
    """TAX-03: which account should pay. Likely not qualified: another way. A spending account whose money is about
    to be forfeited, with the HSA as the alternative. Then the HSA (pay now, or pay another way and keep the receipt
    with "save for later"). Then the only tax-advantaged account that can pay. Then another way."""
    if tag.tag == "likely_not_qualified":
        return Recommendation("other", f"Pay another way: this is likely not a qualified expense ({tag.cite}), so an "
                                       "HSA or FSA probably can't pay it tax-free.")
    year = int(visit_date[:4])
    letter = (f"Get {tag.category.documentation} and keep it with the receipt." if tag.needs_letter else "")
    hsas = [a for a in accounts if a.get("type") == "hsa" and (a.get("opened") or "") <= visit_date
            and may_pay_for(a, member, year)[0] != "no"]
    spending = []
    for a in accounts:
        if a.get("type") in SPENDING and funds_usable(a, visit_date) and covers(a, tag)[0] \
                and may_pay_for(a, member, year)[0] != "no":
            balance, _ = account_balance(a, documents)
            if balance is None or balance > 0:
                spending.append(a)
    for a in spending:
        if f := at_risk(a, documents, today, tables):
            return Recommendation(
                "account", f"Pay from {a['name']}: {fmt(f.amount)} of its balance is forfeited if it isn't used by "
                           f"{f.last_day.isoformat()} ({f.days} days).", a,
                alternative=f"Or pay from {hsas[0]['name']}." if hsas else "", letter=letter)
    if hsas:
        hsa = hsas[0]
        if strategy == "save_for_later":
            return Recommendation("vault", "Pay another way and keep the receipt: the expense goes into the HSA receipt "
                                           f"vault, to reimburse yourself from {hsa['name']} later.", hsa, letter=letter)
        return Recommendation("hsa", f"Pay from {hsa['name']}.", hsa, letter=letter)
    if spending:
        a = spending[0]
        return Recommendation("account", f"Pay from {a['name']}: it's the only tax-advantaged account here that can pay "
                                         "this.", a, letter=letter)
    return Recommendation("other", "Pay another way: no tax-advantaged account here can pay this.", letter=letter)


# ---------- contributions and eligibility (TAX-06, TAX-08) ----------

@dataclass
class Month:
    month: int
    coverage: str | None  # self_only | family | None (no HSA-eligible plan on the 1st)
    blocked: str = ""  # why the holder can't contribute this month (TAX-08)

    @property
    def eligible(self) -> bool:
        return self.coverage is not None and not self.blocked


@dataclass
class Conflict:
    kind: str  # fsa | medicare
    text: str
    months: list[int]
    contributions: list[dict]
    amount: int = 0


@dataclass
class ContributionCheck:
    account: dict
    year: int
    holder: dict | None
    employee: int = 0
    employer: int = 0
    limit: int | None = None  # None when there is no limits row for the year
    catch_up: int = 0
    rule: str = "monthly"  # monthly | last_month
    months: list[Month] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    warning: str = ""
    source: str = ""
    fees: list[dict] = field(default_factory=list)  # the account's fees dated in the year (B-17: a possible saving)

    @property
    def contributed(self) -> int:
        return self.employee + self.employer

    @property
    def room(self) -> int | None:
        return None if self.limit is None else max(self.limit - self.contributed, 0)

    @property
    def excess(self) -> int:
        return 0 if self.limit is None else max(self.contributed - self.limit, 0)

    @property
    def fee_total(self) -> int:
        return sum(d["amount"] for d in self.fees)

    @property
    def eligible_months(self) -> int:
        return sum(m.eligible for m in self.months)


def _covers_day(start: str | None, end: str | None, day: date) -> bool:
    return (not start or _day(start) <= day) and (not end or day <= _day(end))


def _coverage(account: dict, holder: dict | None, plans: list[dict], day: date) -> str | None:
    """Self-only or family HSA-eligible coverage on a day: the account's periods, else the plans covering the holder."""
    if account.get("coverage"):
        return next((c["type"] for c in account["coverage"] if _covers_day(c.get("start"), c.get("end"), day)), None)
    for p in plans:
        if not p.get("hsa_eligible_plan"):
            continue
        members = p.get("member_ids") or []
        if holder and members and holder["id"] not in members:
            continue
        start = p.get("coverage_start") or f"{p['plan_year']}-01-01"
        end = p.get("coverage_end") or f"{p['plan_year']}-12-31"
        if _covers_day(start, end, day):
            return "family" if len(members) > 1 else "self_only"
    return None


def contribution_check(account: dict, year: int, ds: Dataset, tables: TaxTables) -> ContributionCheck:
    """TAX-06 and TAX-08 for one HSA and tax year: what went in, against the limit for the months the holder was
    eligible (monthly pro rata by default, the last-month rule when chosen), and what blocked eligibility."""
    holder = holder_of(account, ds.members)
    check = ContributionCheck(account, year, holder)
    contributions = []
    for d in ds.documents:
        if d["type"] != "account_transaction" or d.get("account_id") != account["id"]:
            continue
        if (d.get("tax_year") or int(d["date"][:4])) != year:
            continue
        if d["kind"] == "fee" and d["date"][:4] == str(year):
            check.fees.append(d)
        if d["kind"] == "contribution_employee":
            check.employee += d["amount"]
            contributions.append(d)
        elif d["kind"] == "contribution_employer":
            check.employer += d["amount"]
            contributions.append(d)
    general_fsas = [a for a in ds.accounts if a.get("type") == "fsa" and plan_period(a)]
    medicare = (holder or {}).get("medicare_from")
    for m in range(1, 13):
        first = date(year, m, 1)
        month = Month(m, _coverage(account, holder, ds.plans, first))
        fsa = next((a for a in general_fsas if plan_period(a)[0] <= first <= plan_period(a)[1]), None)
        if medicare and _day(medicare) <= first:
            month.blocked = "Medicare"
        elif fsa:
            month.blocked = f"general-purpose FSA ({fsa['name']})"
        check.months.append(month)

    for kind, label in (("fsa", "general-purpose FSA"), ("medicare", "Medicare")):
        months = [m.month for m in check.months if m.blocked and (m.blocked == "Medicare") == (kind == "medicare")]
        if not months:
            continue
        hit = [d for d in contributions if int(d["date"][5:7]) in months and int(d["date"][:4]) == year]
        if kind == "medicare":
            text = (f"Medicare from {_day(medicare).isoformat()}: no HSA contributions are allowed from that month "
                    f"on, so the limit leaves those months out.")
        else:
            text = ("A general-purpose health FSA in the household can pay the HSA holder's bills, which blocks HSA "
                    "contributions for its plan year. A limited-purpose FSA doesn't.")
        if hit:
            text += f" {len(hit)} contribution{'s' if len(hit) != 1 else ''} dated in those months."
        check.conflicts.append(Conflict(kind, text, months, hit, sum(d["amount"] for d in hit)))

    limits = tables.limits.get(year)
    if not limits:
        check.notes.append(f"There's no IRS limits table for {year} yet, so contributions can't be checked.")
        return check
    check.source = limits.source
    rates = {"self_only": limits.hsa_self_only, "family": limits.hsa_family}
    age_known = bool(holder and holder.get("birth_year"))
    catch_up = limits.hsa_catch_up if age_known and year - holder["birth_year"] >= CATCH_UP_AGE else 0
    if holder is None:
        check.notes.append("No account holder: set the HSA's holder under Account rules, or a member as 'self'.")
    elif not age_known:
        check.notes.append(f"Add {holder['name']}'s birth year under People to check the 55+ catch-up.")
    if not any(m.coverage for m in check.months):
        check.notes.append("No HSA-eligible coverage found for this year: mark the plan as HSA-eligible in Settings, "
                           "or add coverage periods to the HSA.")
    december = check.months[11]
    chosen = year in (account.get("last_month_rule_years") or [])
    if chosen and not december.eligible:
        check.notes.append("The last-month rule needs HSA-eligible coverage on December 1, so the monthly limit is used.")
    if chosen and december.eligible:
        check.rule = "last_month"
        check.catch_up = catch_up
        check.limit = rates[december.coverage] + catch_up
        check.warning = LAST_MONTH_WARNING.format(next=year + 1)
    else:
        eligible = [m for m in check.months if m.eligible]
        check.catch_up = catch_up * len(eligible) // 12
        check.limit = sum(rates[m.coverage] + catch_up for m in eligible) // 12
    return check


# ---------- the year's tax view: vault, flags, summary (TAX-04, TAX-07, TAX-10) ----------

@dataclass
class VaultEntry:
    visit: VisitResult
    payment: dict
    amount: int
    tag: Tag
    repaid: list[tuple[dict, int]] = field(default_factory=list)  # (account_reimbursement, amount it paid back)

    def outstanding(self, as_of: str | None = None) -> int:
        """What is still to reimburse, or what was on a date."""
        return self.amount - sum(n for r, n in self.repaid if as_of is None or r["date"] <= as_of)

    @property
    def open(self) -> bool:
        return self.outstanding() > 0

    @property
    def reimbursement(self) -> dict | None:
        """The latest reimbursement that paid some of it back."""
        return self.repaid[-1][0] if self.repaid else None


@dataclass
class TaxFlag:
    kind: str  # not_qualified | documentation | person
    amount: int
    text: str
    guidance: str = ""  # mistaken-distribution guidance, only when the member marked it a mistake


@dataclass
class SummaryRow:
    member_id: str
    name: str
    hsa_distributions: int = 0
    by_purpose: dict[str, int] = field(default_factory=dict)
    out_of_pocket: int = 0  # qualified, paid outside HSAs and FSAs and not reimbursed (possible deduction)
    unreimbursed: int = 0  # vault at year end

    def add(self, other: "SummaryRow") -> None:
        self.hsa_distributions += other.hsa_distributions
        self.out_of_pocket += other.out_of_pocket
        self.unreimbursed += other.unreimbursed
        for k, v in other.by_purpose.items():
            self.by_purpose[k] = self.by_purpose.get(k, 0) + v


@dataclass
class YearSummary:
    year: int
    rows: list[SummaryRow]
    family: SummaryRow
    distributions: int  # the HSAs' payments and reimbursements dated in the year
    refunds: int  # money providers returned to an HSA in the year

    @property
    def balanced(self) -> bool:
        return self.family.hsa_distributions == self.distributions


@dataclass
class TaxView:
    year: int
    strategy: str
    today: date
    tags: dict[str, Tag]  # visit id -> tag, every visit
    visits: dict[str, VisitResult]  # visit id -> the visit in its own year's report
    vault: list[VaultEntry]  # every year, newest first
    contributions: list[ContributionCheck]
    flags: dict[str, list[TaxFlag]]  # visit id -> flags, this year's visits
    recommendations: dict[str, Recommendation]  # visit id -> recommendation, this year's visits
    summary: YearSummary
    double_reimbursed: list[str] = field(default_factory=list)  # payment ids reimbursed more than once
    hsa: dict | None = None  # the HSA the vault is for

    def vault_total(self, as_of: str | None = None) -> int:
        """TC-TAX-04-1/3, TC-TAX-10-2: what is still to reimburse, or what was on a date (expenses on or before it,
        less what was reimbursed by then)."""
        return sum(e.outstanding(as_of) for e in self.vault if as_of is None or e.visit.visit["date"] <= as_of)

    @property
    def open_vault(self) -> list[VaultEntry]:
        return [e for e in self.vault if e.open]


def strategy_of(preference: dict | None) -> str:
    value = (preference or {}).get("hsa_strategy")
    return value if value in STRATEGIES else "pay_now"


def tax_view(ds: Dataset, reports: dict[int, Report], year: int, today: date, tables: TaxTables,
             strategy: str = "pay_now") -> TaxView:
    """Everything the HSA and tax page shows for a year. `reports` has one Report per year with activity (the vault
    and the summary need every year's allocations)."""
    providers = {p["id"]: p for p in ds.providers}
    accounts = {a["id"]: a for a in ds.accounts}
    members = {m["id"]: m for m in ds.members}
    receipts = defaultdict(list)
    for d in ds.documents:
        if d["type"] == "receipt":
            receipts[d["visit_id"]].append(d)
    hsas = sorted((a for a in ds.accounts if a.get("type") == "hsa"), key=lambda a: a["id"])
    hsa = hsas[0] if hsas else None

    def kind(account_id: str) -> str:
        return accounts.get(account_id, {}).get("type", "")

    # Reimbursements (from the HSA or another account), oldest first, by the payments they name.
    reimbursements = sorted((d for d in ds.documents if d["type"] == "account_reimbursement"),
                            key=lambda d: (d["date"], d["id"]))
    reimbursed: dict[str, list[dict]] = defaultdict(list)
    for r in reimbursements:
        for pid in r["payment_ids"]:
            reimbursed[pid].append(r)

    # Every visit once, in its own year's report; every allocation once, in its payment's year's report.
    visits: dict[str, VisitResult] = {}
    allocations: list[tuple[VisitResult, Allocation]] = []
    by_payment: dict[str, list[tuple[VisitResult, Allocation]]] = defaultdict(list)
    for y, report in reports.items():
        for g in report.groups:
            for vr in g.visits:
                if int(vr.visit["date"][:4]) == y or vr.id not in visits:
                    visits[vr.id] = vr
                for a in vr.allocations:
                    allocations.append((vr, a))
                    if not a.refund:
                        by_payment[a.payment["id"]].append((vr, a))
    tags = {vid: tag_visit(vr.visit, providers.get(vr.visit["provider_id"]), receipts.get(vid, []), tables)
            for vid, vr in visits.items()}

    # The receipt vault (TAX-04)
    vault = []
    if hsa:
        for vr, a in allocations:
            if a.refund or a.surplus or kind(a.payment["account_id"]) in TAX_ADVANTAGED:
                continue
            tag = tags[vr.id]
            if not tag.qualified or vr.visit["date"] < (hsa.get("opened") or ""):
                continue
            if may_pay_for(hsa, members.get(vr.visit.get("member_id")), int(vr.visit["date"][:4]))[0] == "no":
                continue
            vault.append(VaultEntry(vr, a.payment, a.amount, tag))
    vault.sort(key=lambda e: (e.visit.visit["date"], e.payment["date"], e.payment["id"]))
    # Each reimbursement pays back its payments' entries, oldest first; a part paid back stays open for the rest.
    # Money for a payment whose entries were already paid back in full is a second reimbursement (TC-TAX-04-3).
    entries = defaultdict(list)
    for e in vault:
        entries[e.payment["id"]].append(e)
    double = []
    for r in reimbursements:
        left = r["amount"]
        for pid in r["payment_ids"]:
            if entries[pid] and all(not e.open for e in entries[pid]):
                double.append(pid)
            for e in entries[pid]:
                take = min(e.outstanding(), left)
                if take > 0:
                    e.repaid.append((r, take))
                    left -= take
    vault.reverse()

    # HSA money that went to each visit in the year: HSA payments dated in it, and payments the HSA reimbursed in it,
    # whatever year the visit is from (an earlier visit paid this year is checked this year).
    ys = str(year)
    hsa_in_year: dict[str, int] = defaultdict(int)
    for vr, a in allocations:
        if a.refund:
            continue
        if kind(a.payment["account_id"]) == "hsa":
            if a.payment["date"][:4] == ys:
                hsa_in_year[vr.id] += a.amount
        elif any(kind(r["from_account_id"]) == "hsa" and r["date"][:4] == ys for r in reimbursed.get(a.payment["id"], [])):
            hsa_in_year[vr.id] += a.amount

    # Flags (TAX-07, TAX-09) and recommendations for the year's visits (TAX-03)
    flags: dict[str, list[TaxFlag]] = {}
    for vid, paid in sorted(hsa_in_year.items()):
        vr = visits[vid]
        tag, member = tags[vid], members.get(vr.visit.get("member_id"))
        out = []
        vyear = int(vr.visit["date"][:4])
        if paid and tag.tag == "likely_not_qualified":
            mistake = bool((vr.visit.get("tax") or {}).get("mistake"))
            out.append(TaxFlag("not_qualified", paid, (
                f"The HSA paid {fmt(paid)} for something that's likely not a qualified expense ({tag.cite}). "
                + ("You marked it a mistake." if mistake else
                   "If it was a mistake, mark it so below to see how to return it.")),
                guidance=MISTAKE_GUIDANCE if mistake else ""))
        elif paid and tag.needs_letter:
            out.append(TaxFlag("documentation", paid, (
                f"The HSA paid {fmt(paid)} for something that needs documentation ({tag.cite}). Get "
                f"{tag.category.documentation} and keep it with the receipt.")))
        if paid and hsa:
            answer, why = may_pay_for(hsa, member, vyear)
            if answer == "no":
                out.append(TaxFlag("person", paid, f"The HSA paid {fmt(paid)} for {member['name']}. {why}"))
        if out:
            flags[vid] = out
    recs = {vr.id: recommend(tags[vr.id], members.get(vr.visit.get("member_id")), vr.visit["date"], ds.accounts,
                             ds.documents, strategy, today, tables)
            for vr in (reports[year].visits if year in reports else [])}

    contributions = [contribution_check(a, year, ds, tables) for a in hsas]
    summary = _summary(year, reports, members, accounts, tags, by_payment, reimbursed, vault, ds.documents)
    return TaxView(year, strategy, today, tags, visits, vault, contributions, flags, recs, summary,
                   sorted(set(double)), hsa)


def _summary(year: int, reports: dict[int, Report], members: dict, accounts: dict, tags: dict[str, Tag],
             by_payment: dict, reimbursed: dict[str, list[dict]], vault: list[VaultEntry],
             documents: list[dict]) -> YearSummary:
    """TAX-10: HSA distributions by person and purpose (adding up to the accounts' distributions), the vault at year
    end, and out-of-pocket qualified spending for a possible itemized deduction."""
    rows: dict[str, SummaryRow] = {mid: SummaryRow(mid, m["name"]) for mid, m in members.items()}
    ys, year_end = str(year), f"{year}-12-31"

    def row(vr: VisitResult | None) -> SummaryRow:
        if vr is None:
            key, name = UNMATCHED, "Not matched to a visit"
        else:
            key = vr.visit.get("member_id") or NOBODY
            key, name = (key, "") if key in members else (NOBODY, "Not assigned to anyone")
        if key not in rows:
            rows[key] = SummaryRow(key, name)
        return rows[key]

    used: dict[tuple[str, int], int] = defaultdict(int)  # (payment id, allocation) -> HSA money attributed to it

    def distribute(amount: int, payment_id: str) -> int:
        """Attribute HSA money to the visits a payment was applied to, each allocation's amount at most once across
        payments and reimbursements; returns what is left unmatched."""
        for n, (vr, a) in enumerate(by_payment.get(payment_id, [])):
            share = min(a.amount - used[(payment_id, n)], amount)
            if share <= 0:
                continue
            used[(payment_id, n)] += share
            r = row(vr)
            r.hsa_distributions += share
            purpose = tags[vr.id].category.name
            r.by_purpose[purpose] = r.by_purpose.get(purpose, 0) + share
            amount -= share
        return amount

    def is_hsa(account_id: str) -> bool:
        return accounts.get(account_id, {}).get("type") == "hsa"

    distributions = refunds = 0
    for d in sorted(documents, key=lambda d: (d["date"], d["id"])):
        if d["date"][:4] != ys:
            continue
        if d["type"] == "payment" and is_hsa(d["account_id"]):
            if d.get("kind") == "refund":
                refunds += d["amount"]
                continue
            distributions += d["amount"]
            left = distribute(d["amount"], d["id"])
        elif d["type"] == "account_reimbursement" and is_hsa(d["from_account_id"]):
            distributions += d["amount"]
            left = d["amount"]
            for pid in d["payment_ids"]:
                left = distribute(left, pid)
        else:
            continue
        if left:
            r = row(None)
            r.hsa_distributions += left
            r.by_purpose["Not matched to a visit"] = r.by_purpose.get("Not matched to a visit", 0) + left

    # Out of pocket: payments dated in the year from accounts that aren't tax-advantaged, applied to qualified
    # visits, not reimbursed from any account, net of refunds to those accounts.
    for report in reports.values():
        for g in report.groups:
            for vr in g.visits:
                if not tags[vr.id].qualified:
                    continue
                for a in vr.allocations:
                    p = a.payment
                    if p["date"][:4] != ys or a.surplus or accounts.get(p["account_id"], {}).get("type") in TAX_ADVANTAGED:
                        continue
                    if p["id"] in reimbursed and not a.refund:
                        continue
                    row(vr).out_of_pocket += -a.amount if a.refund else a.amount
    for e in vault:
        if e.visit.visit["date"] <= year_end:
            row(e.visit).unreimbursed += e.outstanding(year_end)

    for key, r in rows.items():
        if not r.name:
            r.name = members[key]["name"]
    people = [r for r in rows.values()]
    family = SummaryRow("family", "Household")
    for r in people:
        family.add(r)
    return YearSummary(year, people, family, distributions, refunds)
