"""The laptop demo (docs/DEMO.md): `mhs-admin demo-setup`, the single-use enrolment link with its SVG QR code,
and the demo pack in samples/demo/ telling its story through the upload pipeline."""

import importlib.util
import io
import re
import secrets
import shutil
from pathlib import Path

import pyotp
import pytest
from PIL import Image

from mhs.data.household_store import HouseholdStore
from mhs.web.household import admin, security
from mhs.web.household.qr import qr_svg
from tests.conftest import Enrolled, admin_sql
from tests.test_r1_scenarios import Member
from tests.test_web import CsrfClient

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "samples" / "demo"


def raster(svg: str, px: int = 8) -> Image.Image:
    """Draw the QR SVG's path (rows of horizontal runs, as segno writes it) as an image a scanner can read."""
    size = int(re.search(r'viewBox="0 0 (\d+) \d+"', svg).group(1))
    d = re.search(r'<path stroke="#000" d="([^"]+)"', svg).group(1)
    img = Image.new("L", (size * px, size * px), 255)
    x = y = 0.0
    for cmd, args in re.findall(r"([Mmh])([-\d.\s]+)", d):
        n = [float(a) for a in args.split()]
        if cmd == "M":
            x, y = n
        elif cmd == "m":
            x, y = x + n[0], y + n[1]
        else:
            img.paste(0, (int(x * px), int((y - .5) * px), int((x + n[0]) * px), int((y + .5) * px)))
            x += n[0]
    return img


def decode(svg: str) -> str:
    zxingcpp = pytest.importorskip("zxingcpp")
    [found] = zxingcpp.read_barcodes(raster(svg))
    assert found.format == zxingcpp.BarcodeFormat.QRCode
    return found.text


def test_qr_svg_scans_and_is_csp_clean():
    uri = pyotp.TOTP(pyotp.random_base32()).provisioning_uri(name="demo@example.com", issuer_name="My Health Spend")
    svg = qr_svg(uri)
    assert decode(svg) == uri
    assert svg.startswith("<svg") and 'viewBox="0 0 ' in svg and "width=" not in svg  # scales to its box
    assert not re.search(r"\sstyle=|<script|\son[a-z]+=|https?://", svg)  # nothing the CSP would block


@pytest.fixture
def cli_env(household, pgdb, tmp_path, monkeypatch):
    """mhs-admin pointed at the test database and the household app's key file."""
    monkeypatch.setenv("MHS_DATABASE_URL", pgdb.url("app"))
    monkeypatch.setenv("MHS_KEY_FILE", str(tmp_path / "keys" / "app.kek"))  # the app_keys fixture's file
    monkeypatch.setenv("MHS_OBJECTS_DIR", str(household.objects_dir))
    monkeypatch.setenv("MHS_PUBLIC_URL", "http://demo.test:3063/")
    return household


def run_demo_setup(capsys, *args: str) -> dict:
    admin.main(["demo-setup", *args])
    out = capsys.readouterr().out
    found = {k: re.search(rf"^\s*{k}:\s+(\S+)$", out, re.M) for k in ("email", "password", "secret", "QR code")}
    values = {k: m.group(1) for k, m in found.items() if m}
    values["household_id"] = re.search(r"\(([0-9a-f-]{36})\) is ready", out).group(1)
    values["out"] = out
    return values


def sign_in(household, email: str, password: str, totp_secret: str):
    who = Enrolled("", "", email, password, totp_secret)
    return household.sign_in(who)


def test_demo_setup_creates_a_ready_household_and_can_rerun(cli_env, pgdb, capsys):
    household = cli_env
    first = run_demo_setup(capsys)
    assert first["email"] == admin.DEMO_EMAIL and len(first["password"]) >= 12
    assert first["QR code"].startswith("http://demo.test:3063/enrol/")
    assert household.accounts.household_name(first["household_id"]) == admin.DEMO_HOUSEHOLD

    c = sign_in(household, first["email"], first["password"], first["secret"])
    settings = c.get("/settings").text
    assert "Jordan Sample" in settings and "Example HDHP 1700" in settings and "HSA" in settings

    # A member edit in Settings, then a rerun: same household and member, Settings put back, new credentials.
    c.post("/settings/members", data={"id": "mbr-jordan-sample", "name": "Jordan Renamed", "relationship": "self",
                                      "csrf_token": household.csrf(c)})
    second = run_demo_setup(capsys)
    assert second["household_id"] == first["household_id"]
    assert (second["password"], second["secret"]) != (first["password"], first["secret"])
    assert c.get("/", follow_redirects=False).status_code == 303  # the old session ended
    assert household.accounts.check_password(first["email"], first["password"]) is None
    assert not household.accounts.enrolment_link_valid(first["QR code"].rsplit("/", 1)[1])  # cancelled by the new secret
    c = sign_in(household, second["email"], second["password"], second["secret"])
    assert "Jordan Renamed" not in c.get("/settings").text and "Jordan Sample" in c.get("/settings").text
    assert admin_sql(pgdb, "SELECT count(*) FROM app.households WHERE name = %s", (admin.DEMO_HOUSEHOLD,))[0][0] == 1


def test_demo_setup_refuses_an_email_from_another_household(cli_env, capsys):
    other = cli_env.enrol("Someone else")
    with pytest.raises(SystemExit, match="member of another household"):
        admin.main(["demo-setup", "--email", other.email])


def test_add_member_prints_an_enrolment_link(cli_env, capsys, monkeypatch):
    hid = cli_env.accounts.create_household("Linked")
    monkeypatch.setattr("sys.stdin", io.StringIO("a long enough password\n"))
    admin.main(["add-member", "--household", hid, "--email", "new@example.test", "--name", "New", "--password-stdin"])
    out = capsys.readouterr().out
    token = re.search(r"QR code: http://demo.test:3063/enrol/(\S+)", out).group(1)
    assert cli_env.accounts.enrolment_link_valid(token)


def test_enrolment_link_shows_the_qr_code_once(household):
    who = household.enrol()
    token = household.accounts.create_enrolment_link(who.email)
    anon = household.client()

    offer = anon.get(f"/enrol/{token}")
    assert offer.status_code == 200 and "Show my QR code" in offer.text
    assert who.totp_secret not in offer.text and "<svg" not in offer.text.split("<main>")[1]  # opening isn't using
    assert offer.headers["content-security-policy"] == security.CSP and offer.headers["cache-control"] == "no-store"

    shown = anon.post(f"/enrol/{token}")
    assert shown.status_code == 200
    svg = re.search(r'<svg viewBox="[^"]+" class="qr">.*?</svg>', shown.text, re.S).group(0)
    assert decode(svg) == household.accounts.provisioning_uri(who.email, who.totp_secret)
    assert " ".join(who.totp_secret[i:i + 4] for i in range(0, len(who.totp_secret), 4)) in shown.text

    for again in (anon.post(f"/enrol/{token}"), anon.get(f"/enrol/{token}")):
        assert again.status_code == 404 and "used or has expired" in again.text and who.totp_secret not in again.text
    household.sign_in(who)  # the code from the QR signs in


def test_enrolment_links_expire_and_end_with_a_new_secret(household):
    who = household.enrol()
    expired = household.accounts.create_enrolment_link(who.email, minutes=0)
    anon = household.client()
    assert anon.get(f"/enrol/{expired}").status_code == 404
    assert anon.post(f"/enrol/{expired}").status_code == 404
    assert anon.post("/enrol/not-a-real-token-at-all-xyz").status_code == 404
    assert anon.get("/enrol/<script>").status_code == 404

    pending = household.accounts.create_enrolment_link(who.email)
    new_secret = household.accounts.reset_mfa(who.email)
    shown = anon.post(f"/enrol/{pending}")
    assert shown.status_code == 404 and new_secret not in shown.text


# --- the demo pack tells its story -------------------------------------------------------------------------

class DemoMember(Member):
    """The demo member, set up by demo-setup instead of through Settings."""

    def __init__(self, household, app_db, worker_db):
        password = secrets.token_urlsafe(12)
        household_id, totp_secret = admin.demo_setup(household.accounts, password)
        self.who = Enrolled(household_id, "", admin.DEMO_EMAIL, password, totp_secret)
        raw = household.sign_in(self.who)
        self.client = CsrfClient(raw, household.csrf(raw))
        self.store = HouseholdStore(app_db, household_id)
        self.worker_db = worker_db
        self.objects_dir = household.objects_dir


def test_demo_pack_matches_its_generator(tmp_path):
    tool = ROOT / "tools" / "make_demo_pack.py"
    if not tool.exists():
        pytest.skip("tools/ isn't in the tests image")
    spec = importlib.util.spec_from_file_location("make_demo_pack", tool)
    pack = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pack)
    pack.write_pack(tmp_path)
    for name in pack.FILES:
        if not name.endswith(".png"):  # PNG bytes vary with the Pillow build; its text is checked by OCR below
            assert (tmp_path / name).read_bytes() == (PACK / name).read_bytes(), f"rerun tools/make_demo_pack.py: {name}"


def test_demo_story(make_household, app_db, worker_db):
    """docs/DEMO.md, step by step: statement, EOB, phone photo of a second EOB, HSA export."""
    ocr = bool(shutil.which("tesseract"))
    m = DemoMember(make_household(ocr_engine="tesseract", scrubber="presidio") if ocr else make_household(),
                   app_db, worker_db)

    sid = m.upload_id(m.upload("1-riverbend-statement.pdf", (PACK / "1-riverbend-statement.pdf").read_bytes()))
    m.work()
    text, values = m.review(sid)
    assert values["balance_due"] == "480.00" and values["member_id"] == "mbr-jordan-sample"
    assert values["provider"] == "Riverbend Orthopedics"
    assert m.confirm(sid, values).headers["location"] == "/visits/v-2026-08-14-riverbend-orthopedics"

    eid = m.upload_id(m.upload("2-riverbend-eob.pdf", (PACK / "2-riverbend-eob.pdf").read_bytes()))
    m.work()
    text, values = m.review(eid)
    assert values["visit_id"] == "v-2026-08-14-riverbend-orthopedics"
    assert values["plan_id"] == "plan-2026-example-hdhp-1700" and values["patient_responsibility"] == "300.00"
    assert m.confirm(eid, values).status_code == 303

    pid = m.upload_id(m.upload("3-lakeside-eob-photo.png", (PACK / "3-lakeside-eob-photo.png").read_bytes(),
                               kind="auto" if ocr else "eob", ctype="image/png"))
    m.work()
    text, values = m.review(pid)
    if ocr:  # on the compose tests runner
        assert "OCR (tesseract)" in text and values["provider"] == "Lakeside Imaging"
        assert (values["billed"], values["patient_responsibility"]) == ("1850.00", "800.00")
    else:  # no OCR engine here: typed by hand, as the review page asks
        values.update(provider="Lakeside Imaging", service_start="2026-09-22", processed_date="2026-10-02",
                      billed="1850.00", adjustment="1050.00", allowed="800.00", insurer_paid="0.00",
                      deductible="800.00", patient_responsibility="800.00", claim_number="C-2026-0922",
                      network_status="in_network", member_id="mbr-jordan-sample")
    assert m.confirm(pid, values).headers["location"] == "/visits/v-2026-09-22-lakeside-imaging"

    m.import_export("4-hsa-transactions.csv", (PACK / "4-hsa-transactions.csv").read_bytes())
    [payment] = [d for d in m.store.all("document") if d["type"] == "payment"]
    assert (payment["amount"], payment["provider_id"]) == (48000, "prov-riverbend-orthopedics")

    riverbend = m.client.get("/visits/v-2026-08-14-riverbend-orthopedics").text
    assert "Discrepancy" in riverbend
    assert "statement of 2026-09-10 asks $480.00, EOB says you owe $300.00" in riverbend
    assert "Payments of $480.00 applied" in riverbend and "HSA" in riverbend
    lakeside = m.client.get("/visits/v-2026-09-22-lakeside-imaging").text
    assert "Balance outstanding" in lakeside and "$800.00 unpaid per insurer" in lakeside
    home = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.client.get("/?year=2026").text))
    assert "$ at stake $180.00" in home and "Unpaid — pay from HSA · 1 visit $800.00" in home
    # The statement-first visit takes its plan from the EOB, so both claims count toward the deductible.
    assert "Jordan Sample in-network deductible $1,100.00 of $1,700.00" in home
