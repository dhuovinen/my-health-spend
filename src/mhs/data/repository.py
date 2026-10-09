"""Load the stored records into the engine's Dataset."""

from mhs.core.reconcile import Dataset
from mhs.data.store import Store


def load_dataset(store: Store) -> Dataset:
    return Dataset(
        plans=store.all("plan"),
        accounts=store.all("account"),
        members=store.all("member"),
        providers=store.all("provider"),
        relationships=store.all("provider_relationship"),
        visits=store.all("visit"),
        documents=store.all("document"),
    )
