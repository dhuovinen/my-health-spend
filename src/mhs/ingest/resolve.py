"""Match names found in uploads to the household's providers, members, plans and accounts.

New providers become records the preview shows, so nothing is dropped; the member can merge them by adding an
alias in Settings. Pure functions over record lists.
"""

import re


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "item"


def norm_name(text: str) -> str:
    """Case, punctuation and spacing don't matter when matching names."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


class Providers:
    def __init__(self, providers: list[dict]):
        self.records = {p["id"]: p for p in providers}
        self.by_name = {norm_name(n): p["id"] for p in providers for n in [p["name"], *p.get("aliases", [])]}
        self.new: dict[str, dict] = {}

    def find(self, name: str) -> str | None:
        return self.by_name.get(norm_name(name))

    def resolve(self, name: str) -> str:
        """The id of the provider with this name or alias, or a new provider record."""
        pid = self.find(name)
        if pid:
            return pid
        pid = "prov-" + slug(name)
        while pid in self.records and norm_name(self.records[pid]["name"]) != norm_name(name):
            pid += "-x"
        record = {"id": pid, "name": name.strip(), "network_status": "unknown", "aliases": [name.strip()]}
        self.records[pid], self.new[pid] = record, record
        self.by_name[norm_name(name)] = pid
        return pid


class Members:
    def __init__(self, members: list[dict]):
        self.by_name = {}
        for m in members:
            for n in [m["name"], *m.get("aliases", [])]:
                self.by_name[norm_name(n)] = m["id"]
                parts = norm_name(n).split()
                if len(parts) >= 2:  # "Smith, Pat" and "Pat Smith" are the same person
                    self.by_name[" ".join([parts[-1], *parts[:-1]])] = m["id"]

    def find(self, name: str) -> str | None:
        n = re.sub(r"\s*\(\d{4}-\d{2}-\d{2}\)$", "", name or "")  # some exports append a date of birth
        return self.by_name.get(norm_name(n))


def plan_for(plans: list[dict], year: int, kind: str = "medical") -> str | None:
    """The plan for a service year: one whose name mentions the kind, else the primary one, else the only one."""
    same_year = [p for p in plans if p.get("plan_year") == year]
    named = [p for p in same_year if kind.lower() in (p.get("plan_name", "") + " " + p["id"]).lower()]
    primary = [p for p in same_year if p.get("coverage_order") == "primary"]
    for group in (named, primary, same_year if len(same_year) == 1 else []):
        if group:
            return group[0]["id"]
    return None


def hsa_account(accounts: list[dict]) -> tuple[str, dict | None]:
    """The household's HSA account id, and a new account record if there isn't one yet."""
    for a in accounts:
        if a.get("type") == "hsa":
            return a["id"], None
    return "acct-hsa", {"id": "acct-hsa", "name": "HSA", "type": "hsa"}
