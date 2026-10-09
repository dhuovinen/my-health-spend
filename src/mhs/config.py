"""Paths and runtime settings. Override the data folder with MHS_DATA_DIR and the port with MHS_PORT."""

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schema" / "mhs-ingest.schema.json"
HOST = "127.0.0.1"  # personal health data, no auth: never bind to other interfaces
PORT = int(os.environ.get("MHS_PORT", "3062"))


@dataclass(frozen=True)
class Config:
    data_dir: Path

    @property
    def db_path(self) -> Path:
        return self.data_dir / "mhs.db"

    @property
    def documents_dir(self) -> Path:
        return self.data_dir / "documents"

    @property
    def settings_file(self) -> Path:
        return self.data_dir / "settings.json"


def load_config() -> Config:
    return Config(data_dir=Path(os.environ.get("MHS_DATA_DIR", ROOT / "data")).resolve())
