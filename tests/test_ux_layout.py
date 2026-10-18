"""UX-10 in a real browser (ADR-041): headless Chromium through Playwright, at a 375px phone and a 1280px desktop,
on both apps, with the synthetic household (samples/household-ingest.json).

TC-UX-10-1: at 375px no page scrolls sideways, every tap target is at least 44px (links inside a sentence excepted,
as WCAG 2.5.8 does), the pages sit in a bottom bar within thumb reach, and on Release 1 a photo taken with the
"Take a photo" button uploads on its own and its review page fits the phone. TC-UX-10-2: at 1280px the six-line
visit shows every panel, the line comparison whole, without zooming or sideways scrolling.

Skips where Playwright's Chromium isn't installed (`uv run playwright install chromium`). Set MHS_UX_SCREENSHOTS to
a folder to keep full-page screenshots of each page checked.
"""

import os
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from mhs.config import Config
from mhs.web.app import create_app
from tests.test_ux import HOUSEHOLD, PEDS, import_household

pytestmark = pytest.mark.browser

playwright_api = pytest.importorskip("playwright.sync_api")

PHONE = {"viewport": {"width": 375, "height": 812}, "is_mobile": True, "has_touch": True, "device_scale_factor": 2}
DESKTOP = {"viewport": {"width": 1280, "height": 800}}
PAGES = ["/", "/visits?year=2026", f"/visits/{PEDS}", "/visits/v-2026-04-02-pcp", "/household", "/providers",
         "/providers/prov-peds?year=2026", "/settings", "/help", "/import", "/cases", f"/visits/{PEDS}/cases/case-1"]
R1_PAGES = ["/uploads", "/account", "/data"]
SHOTS = os.environ.get("MHS_UX_SCREENSHOTS")

# Every visible control smaller than 44px in either direction, except a link inside running text.
SMALL_TARGETS = """() => {
  const out = [];
  for (const el of document.querySelectorAll('a[href], button, input:not([type=hidden]), select, textarea, summary')) {
    let target = el;
    if (el.matches('input[type=checkbox], input[type=radio], input.visually-hidden')) target = el.closest('label') || el;
    const r = target.getBoundingClientRect();
    if (!r.width || !r.height || getComputedStyle(target).visibility === 'hidden') continue;
    if (el.tagName === 'A' && getComputedStyle(el).display === 'inline') {
      const words = [...el.parentElement.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join('');
      if (words) continue;
    }
    if (r.height < 43.5 || r.width < 43.5)
      out.push(`${el.tagName.toLowerCase()} "${(el.textContent || el.name || '').trim().slice(0, 40)}" ${Math.round(r.width)}x${Math.round(r.height)}`);
  }
  return out;
}"""
SIDEWAYS = "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"


@pytest.fixture(scope="module")
def browser():
    with playwright_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # no browser downloaded
            pytest.skip(f"Chromium for Playwright isn't installed: {str(e).splitlines()[0]}")
        yield b
        b.close()


class Server:
    """Serve an ASGI app on a free loopback port in a thread, for the browser."""

    def __init__(self, app):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        deadline = time.time() + 10
        while not self.server.started:
            assert time.time() < deadline, "server didn't start"
            time.sleep(0.05)
        self.url = f"http://127.0.0.1:{self.port}"

    def stop(self):
        self.server.should_exit = True
        self.thread.join(5)


@pytest.fixture
def release0(tmp_path):
    from tests.test_web import ReleaseZero

    config = Config(data_dir=tmp_path / "data")
    r0 = ReleaseZero(config)
    import_household(r0)
    open_case(r0.client)
    server = Server(create_app(config))
    yield server, []
    server.stop()


@pytest.fixture
def release1(household, app_db, worker_db):
    from tests.test_r1_scenarios import Member
    from tests.test_web import ReleaseOne

    member = Member(household, app_db, worker_db)
    r1 = ReleaseOne.__new__(ReleaseOne)
    r1.client = member.client
    import_household(r1)
    open_case(r1.client)
    server = Server(household.app)
    cookie = {"name": "mhs_session", "value": member.client.client.cookies.get("mhs_session"), "url": server.url}
    yield server, [cookie], member
    server.stop()


def open_case(client):
    """A dispute case with a logged call, for the case and Cases pages (ADR-042)."""
    assert client.post(f"/visits/{PEDS}/cases", data={"finding": "all"}, follow_redirects=False).status_code == 303
    client.post(f"/visits/{PEDS}/cases/case-1/contacts", data={"channel": "phone", "person": "Dana", "reference": "R-1",
                                                               "outcome": "Will send a corrected bill"})


def open_page(browser, server, cookies, device):
    context = browser.new_context(**device)
    if cookies:
        context.add_cookies(cookies)
    return context, context.new_page()


def shot(page, name: str):
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / name), full_page=True)


def check_phone(page, base: str, paths: list[str], label: str):
    problems = {}
    for path in paths:
        response = page.goto(base + path)
        assert response.status == 200, path
        found = []
        if (extra := page.evaluate(SIDEWAYS)) > 0:
            found.append(f"page scrolls sideways by {extra}px")
        found += page.evaluate(SMALL_TARGETS)
        tabbar = page.locator("nav.tabbar")
        assert tabbar.is_visible(), path
        box = tabbar.bounding_box()
        assert box["y"] + box["height"] >= 812 - 1 and box["height"] >= 44, path  # at the bottom, within thumb reach
        assert not page.locator("header nav.nav").is_visible(), path
        if found:
            problems[path] = found
        shot(page, f"{label}-375{path.replace('/', '_').replace('?', '_')}.png")
    assert not problems, "\n".join(f"{p}: {f}" for p, f in problems.items())


def check_desktop_visit(page, base: str, label: str):
    page.goto(base + f"/visits/{PEDS}")
    assert page.evaluate(SIDEWAYS) <= 0
    assert page.locator("header nav.nav").is_visible() and not page.locator("nav.tabbar").is_visible()
    for section in ("findings", "lines", "allocation", "documents", "history", "notes"):
        box = page.locator(f"#{section}").bounding_box()
        assert box and box["width"] >= 400 and box["x"] >= 0 and box["x"] + box["width"] <= 1280, section
    # the six-line comparison fits its card: no scrolling inside it, every row on the page
    wrap = page.locator("#lines .table-wrap").first
    assert wrap.evaluate("el => el.scrollWidth - el.clientWidth") <= 0
    assert page.locator("#lines table.line-compare tbody tr").count() == 6
    assert page.locator("#lines tr.disagree").count() == 1
    # findings and who-pays-what side by side
    f, a = page.locator("#findings").bounding_box(), page.locator("#allocation").bounding_box()
    assert abs(f["y"] - a["y"]) < 2 and f["x"] < a["x"]
    shot(page, f"{label}-1280-visit.png")
    for path in ("/", "/household"):
        page.goto(base + path)
        assert page.evaluate(SIDEWAYS) <= 0, path
        shot(page, f"{label}-1280{path.replace('/', '_')}.png")


def test_tc_ux_10_1_phone_release0(browser, release0):
    server, cookies = release0
    context, page = open_page(browser, server, cookies, PHONE)
    check_phone(page, server.url, PAGES, "r0")
    assert page.locator("nav.tabbar a.add").get_attribute("href") == "/import"
    context.close()


def test_tc_ux_10_2_desktop_release0(browser, release0):
    server, cookies = release0
    context, page = open_page(browser, server, cookies, DESKTOP)
    check_desktop_visit(page, server.url, "r0")
    context.close()


@pytest.mark.postgres
def test_tc_ux_10_1_phone_release1_capture_and_review(browser, release1):
    """Capture a photo with one tap, review an upload and the visit list at 375px."""
    from tests.pdfs import make_image, make_pdf
    from tests.test_r1_scenarios import STATEMENT

    server, cookies, member = release1
    context, page = open_page(browser, server, cookies, PHONE)
    page.goto(server.url + "/")
    page.locator("nav.tabbar a.add").click()
    assert page.url.endswith("/uploads")
    camera = page.locator("form.camera input[type=file]")
    assert camera.get_attribute("capture") == "environment" and camera.get_attribute("accept") == "image/*"
    button = page.locator("form.camera label.camera-btn")
    assert button.is_visible() and button.bounding_box()["height"] >= 44
    with page.expect_navigation():
        camera.set_input_files({"name": "photo.png", "mimeType": "image/png", "buffer": make_image(STATEMENT)})
    assert "uploaded=" in page.url and "being read now" in page.content()
    # a PDF through the other form, read by the worker, reviewed on the phone
    page.locator("form.inline input[type=file]").set_input_files(
        {"name": "statement.pdf", "mimeType": "application/pdf", "buffer": make_pdf(STATEMENT)})
    with page.expect_navigation():
        page.locator("form.inline button[type=submit]").click()
    member.work()
    page.goto(server.url + "/uploads")
    review = page.locator("a.btn", has_text="Review").first
    path = review.get_attribute("href")
    check_phone(page, server.url, PAGES + R1_PAGES + [path], "r1")
    page.goto(server.url + path)
    confirm = page.locator("button[type=submit]").last
    assert confirm.bounding_box()["height"] >= 44
    context.close()


@pytest.mark.postgres
def test_tc_ux_10_2_desktop_release1(browser, release1):
    server, cookies, member = release1
    context, page = open_page(browser, server, cookies, DESKTOP)
    check_desktop_visit(page, server.url, "r1")
    context.close()
