import json
from pathlib import Path

import pytest

from mhs.config import ROOT, Config
from mhs.data.importer import commit, prepare
from mhs.data.store import Store

SAMPLE = ROOT / "samples" / "example-ingest.json"


@pytest.fixture
def sample_data() -> dict:
    return json.loads(SAMPLE.read_text())


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(data_dir=tmp_path / "data")


@pytest.fixture
def store(config: Config) -> Store:
    return Store(config.db_path)


@pytest.fixture
def loaded_store(store: Store, config: Config, sample_data: dict) -> Store:
    plan = prepare(sample_data, store, str(SAMPLE), SAMPLE.parent)
    assert plan.ok, plan.errors
    commit(plan, store, config.documents_dir)
    return store
