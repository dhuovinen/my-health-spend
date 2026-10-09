"""Keep data/settings.json in step with the Settings page.

tools/build_ingest.py reads settings.json (plans, members, provider aliases), so every edit made in
the app is written back to it. Otherwise the next converter run and import would undo the edit.
"""

import json
import shutil
from datetime import date
from pathlib import Path

from mhs.data.money import to_dollars
from mhs.data.store import Store

SETTINGS_SECTIONS = {
    "plans": "plan",
    "accounts": "account",
    "members": "member",
    "providers": "provider",
    "provider_relationships": "provider_relationship",
}


def export_settings(store: Store, path: Path) -> None:
    previous_source = {}
    if path.is_file():
        shutil.copyfile(path, path.with_suffix(".json.bak"))
        try:
            previous_source = json.loads(path.read_text()).get("source", {})
        except json.JSONDecodeError:
            pass
    out = {
        "schema_version": "0.1",
        "source": {
            "prepared_by": "My Health Spend Settings page",
            "prepared_on": date.today().isoformat(),
            "notes": previous_source.get("notes", "Settings exported from the app."),
        },
    }
    for section, kind in SETTINGS_SECTIONS.items():
        out[section] = [to_dollars(r) for r in store.all(kind)]
    path.write_text(json.dumps(out, indent=2) + "\n")
