"""Reference tables as dated data (PLT-01, ADR-043): IRS limits by tax year and the Publication 502 categories.

The JSON files beside this module hold dollars; the engine gets cents. Add a year or a category version in the yearly
review (CMP-06); no code changes.
"""

import json
from functools import lru_cache
from pathlib import Path

from mhs.core.tax import Category, CategoryTable, TaxTables, YearLimits
from mhs.data.money import cents

HERE = Path(__file__).parent


def tables_from(limits: dict, categories: dict) -> TaxTables:
    years = {}
    for row in limits["years"]:
        years[row["year"]] = YearLimits(
            year=row["year"], hsa_self_only=cents(row["hsa_self_only"]), hsa_family=cents(row["hsa_family"]),
            hsa_catch_up=cents(row["hsa_catch_up"]), fsa=cents(row["fsa"]), fsa_carryover=cents(row["fsa_carryover"]),
            source=row.get("source", ""))
    versions = []
    for v in categories["versions"]:
        versions.append(CategoryTable(
            version=v["version"], effective_from=v["effective_from"], source=v.get("source", ""),
            categories=tuple(Category(
                id=c["id"], cite=c["cite"], name=c["name"], tag=c["tag"], scope=c.get("scope", "medical"),
                words=tuple(c.get("words", ())), provider_kinds=tuple(c.get("provider_kinds", ())),
                visit_categories=tuple(c.get("visit_categories", ())), documentation=c.get("documentation", ""),
                note=c.get("note", "")) for c in v["categories"])))
    return TaxTables(categories=sorted(versions, key=lambda t: t.effective_from), limits=years)


@lru_cache(maxsize=1)
def load_tables() -> TaxTables:
    return tables_from(json.loads((HERE / "irs_limits.json").read_text()),
                       json.loads((HERE / "pub502_categories.json").read_text()))
