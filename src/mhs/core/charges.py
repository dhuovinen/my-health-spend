"""Provider charges over time (UX-11): one bill per person, provider and service date, as a chart and a table.

Pure functions; no database or web imports. Money in integer cents. The picture is worked out here and drawn as SVG by
the template, so the page needs no chart library and stays within the content security policy.
"""

from dataclasses import dataclass, field
from datetime import date

WIDTH, HEIGHT = 760, 320
LEFT, RIGHT, TOP, BOTTOM = 64, 16, 14, 34
OVERLAP = 18  # dots at one spot sit side by side, so each can be reached (TC-UX-11-12)
VIEWS = {"billed": "Billed", "share": "Your share"}


@dataclass
class Bill:
    visit_id: str
    provider: str
    group_id: str
    member_id: str
    member: str
    date: str
    billed: int | None
    share: int | None
    status: str
    lines: list[dict] = field(default_factory=list)

    def amount(self, view: str) -> int | None:
        return self.share if view == "share" else self.billed


@dataclass
class Dot:
    bill: Bill
    x: float
    y: float
    color: int
    amount: int


@dataclass
class Chart:
    dots: list[Dot]
    y_ticks: list[tuple[float, int]]
    x_ticks: list[tuple[float, str]]
    year_line: float | None
    year_labels: list[tuple[float, str]]


def bill_lines(vr) -> list[dict]:
    """The bill's line items: the EOB's lines when it has them, else the latest statement's."""
    lines = [{"code": line.get("code", ""), "description": line.get("description", ""), "billed": line.get("billed"),
              "allowed": line.get("allowed"), "share": line.get("patient_responsibility")}
             for c in vr.claims for line in c.get("lines") or []]
    if lines or not vr.bill_lines:
        return lines
    newest = vr.bill_lines[0][0]["id"]
    return [{"code": i.get("code", ""), "description": i.get("description", ""), "billed": i.get("charge"),
             "allowed": None, "share": i.get("patient_amount")}
            for bill, line in vr.bill_lines if bill["id"] == newest for i in line.get("items") or []]


def bills_of(visits: list) -> list[Bill]:
    """Newest first. A visit with nothing billed has no billed amount; one with no EOB has no member's share yet."""
    out = [Bill(v.id, v.provider["name"], v.group_id, v.visit.get("member_id") or "",
                v.member["name"] if v.member else "No one assigned", v.visit["date"],
                v.total_billed or None, v.insurer_owed, v.status_label, bill_lines(v))
           for v in visits if not v.carry_in]
    return sorted(out, key=lambda b: (b.date, b.visit_id), reverse=True)


def select(bills: list[Bill], provider: str = "", member: str = "") -> list[Bill]:
    return [b for b in bills if (not provider or b.group_id == provider) and (not member or b.member_id == member)]


def _nice_top(most: int) -> int:
    """A round top for the amount axis, in cents."""
    if most <= 0:
        return 10000
    step = 1000
    while step * 10 < most:
        step *= 10
    for mult in (1, 2, 5, 10):
        if step * mult >= most:
            return step * mult
    return step * 10


def chart(bills: list[Bill], view: str, first: int, last: int, colors: dict[str, int]) -> Chart:
    """Positions for each bill with an amount in this view, from January of `first` to December of `last`."""
    start, end = date(first, 1, 1).toordinal(), date(last, 12, 31).toordinal()
    plotted = [b for b in bills if b.amount(view) is not None]
    top = _nice_top(max((b.amount(view) for b in plotted), default=0))
    width, height = WIDTH - LEFT - RIGHT, HEIGHT - TOP - BOTTOM
    place = lambda d: LEFT + width * (d - start) / (end - start)  # noqa: E731
    seen: dict[tuple[str, int], int] = {}
    dots = []
    for b in sorted(plotted, key=lambda b: (b.date, b.member, b.visit_id)):
        amount = b.amount(view)
        n = seen.get((b.date, amount), 0)
        seen[(b.date, amount)] = n + 1
        x = min(place(date.fromisoformat(b.date).toordinal()) + n * OVERLAP, WIDTH - RIGHT)
        dots.append(Dot(b, round(x, 1), round(TOP + height * (1 - amount / top), 1), colors.get(b.member_id, -1), amount))
    y_ticks = [(round(TOP + height * (1 - i / 4), 1), top * i // 4) for i in range(5)]
    x_ticks = []
    for year in range(first, last + 1):
        for month, label in ((1, "Jan"), (4, "Apr"), (7, "Jul"), (10, "Oct")):
            x_ticks.append((round(place(date(year, month, 1).toordinal()), 1), label))
    year_line = round(place(date(last, 1, 1).toordinal()), 1) if last > first else None
    labels = [(round(place(date(y, 7, 1).toordinal()), 1), str(y)) for y in range(first, last + 1)]
    return Chart(dots, y_ticks, x_ticks, year_line, labels)
