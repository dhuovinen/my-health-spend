"""The product is CareBack (ADR-060, REBRAND_PLAN.md §3): the old name can't creep back into anything a person sees.

Code, package and infrastructure names stay `mhs`, and the old domain stays a forwarding host (ADR-058), so this looks
for the old *name*, not for "mhs" or "myhealthspend.com"."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mhs.config import Config
from mhs.web.app import create_app
from mhs.web.household.auth import TOTP_ISSUER

ROOT = Path(__file__).resolve().parent.parent
OLD_NAME = re.compile(r"Health\s+(?:\$|[Ss])pend|MH\$|class=\"dollar\"")
SHIPPED = [ROOT / "src", ROOT / "schema", ROOT / "pyproject.toml"]
TEXT = {".py", ".html", ".css", ".js", ".json", ".toml", ".txt", ".webmanifest", ".svg", ".md"}


def shipped_files():
    for place in SHIPPED:
        yield from ([place] if place.is_file() else (p for p in place.rglob("*") if p.suffix in TEXT and p.is_file()))


def test_nothing_shipped_names_the_old_brand():
    found = []
    for path in shipped_files():  # the whole file, so a name broken across two lines is caught too
        text = path.read_text(errors="ignore")
        found += [f"{path.relative_to(ROOT)}:{text.count(chr(10), 0, m.start()) + 1}: {m.group()!r}"
                  for m in OLD_NAME.finditer(text)]
    assert found == []


def test_authenticator_label_is_careback():
    """New enrolments show CareBack in the authenticator app; entries made before keep the old label and still work."""
    assert TOTP_ISSUER == "CareBack"


@pytest.fixture
def release0(tmp_path):
    return TestClient(create_app(Config(data_dir=tmp_path / "data")))


@pytest.mark.parametrize("path", ["/", "/visits", "/help", "/settings", "/plan", "/welcome"])
def test_pages_carry_the_new_name(release0, path):
    text = release0.get(path).text
    assert not OLD_NAME.search(text), path
    assert "CareBack" in text, path


def test_page_titles_end_with_the_name(release0):
    assert re.search(r"<title>Help · CareBack</title>", release0.get("/help").text)
    assert 'class="brand" href="/" aria-label="CareBack"' in release0.get("/").text
