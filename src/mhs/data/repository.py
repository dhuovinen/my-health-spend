"""Load the stored records into the engine's Dataset."""

from mhs.core.reconcile import WAITING_DAYS, Dataset
from mhs.data.reference import load_claim_codes
from mhs.data.store import Store

# Household preferences live in their own record kind, which imports never touch.
PREFERENCE = "preference"
RECONCILIATION = "reconciliation"
REVIEW = "review"

# How the review page treats the worker's confidence in each field it read. A field below `check_below` is marked
# "Check"; `show_confidence` is when its percentage is printed: always, only on marked fields, or never.
CHECK_BELOW = (0.8, 0.9, 0.95, 1.0)
SHOW_CONFIDENCE = ("flagged", "always", "never")
REVIEW_DEFAULTS = {"check_below": 0.8, "show_confidence": "flagged"}


def waiting_days(store: Store) -> int:
    """The REC-11 waiting threshold in days (default 30)."""
    pref = store.get(PREFERENCE, RECONCILIATION) or {}
    return int(pref.get("waiting_days") or WAITING_DAYS)


def review_prefs(store: Store) -> dict:
    """The household's review-page settings, falling back to the defaults for anything missing or out of range."""
    pref = store.get(PREFERENCE, REVIEW) or {}
    check = pref.get("check_below")
    show = pref.get("show_confidence")
    return {"check_below": check if check in CHECK_BELOW else REVIEW_DEFAULTS["check_below"],
            "show_confidence": show if show in SHOW_CONFIDENCE else REVIEW_DEFAULTS["show_confidence"]}


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
        claim_codes=load_claim_codes(),
    )
