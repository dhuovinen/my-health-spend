"""Load the stored records into the engine's Dataset."""

from mhs.core.reconcile import WAITING_DAYS, Dataset
from mhs.data.store import Store

# Household preferences live in their own record kind, which imports never touch.
PREFERENCE = "preference"
RECONCILIATION = "reconciliation"


def waiting_days(store: Store) -> int:
    """The REC-11 waiting threshold in days (default 30)."""
    pref = store.get(PREFERENCE, RECONCILIATION) or {}
    return int(pref.get("waiting_days") or WAITING_DAYS)


def load_dataset(store: Store) -> Dataset:
    return Dataset(
        plans=store.all("plan"),
        accounts=store.all("account"),
        members=store.all("member"),
        providers=store.all("provider"),
        relationships=store.all("provider_relationship"),
        visits=store.all("visit"),
        documents=store.all("document"),
        waiting_days=waiting_days(store),
        notes=store.all("provider_note"),
    )
