# verifies one actual website suite run through the dashboard in Chromium

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

pw = pytest.importorskip("playwright.sync_api", reason="Install testbench/requirements.txt to verify the dashboard in Chromium")
expect = pw.expect
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def dashboard_server(tmp_path):
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    with (tmp_path / "dashboard.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "testbench/serve_testbench.py"), "--port", str(port)],
            cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        with httpx.Client(base_url=url, trust_env=False, timeout=3) as client:
            try:
                until = time.monotonic() + 15
                while time.monotonic() < until and process.poll() is None:
                    try:
                        if client.get("/api/config").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    pytest.fail(f"Dashboard did not start; see {tmp_path / 'dashboard.log'}")
                yield url, client
            finally:
                if process.poll() is None:
                    try:
                        if client.get("/api/job").json().get("job", {}).get("status") == "running":
                            client.post("/api/job/cancel", timeout=15)
                    except (httpx.HTTPError, AttributeError):
                        pass
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)


def test_dashboard_runs_suite_filters_evidence_and_fits_mobile(page, dashboard_server):
    url, client = dashboard_server
    page_errors = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.set_viewport_size({"width": 1440, "height": 1050})
    page.goto(url)
    expect(page.get_by_role("heading", name="Website test bench.")).to_be_visible()
    expect(page.locator("#connection")).to_have_text("Connected")
    page.locator(".mode").filter(has=page.locator("input[value=smoke]")).click()
    expect(page.locator("#target-url")).to_be_visible()
    expect(page.locator("#known-field")).to_be_hidden()
    page.locator(".mode").filter(has=page.locator("input[value=live]")).click()
    expect(page.locator("#console-url")).to_be_visible()
    page.locator(".mode").filter(has=page.locator("input[value=local]")).click()
    expect(page.locator("#target-field")).to_be_hidden()
    page.get_by_role("button", name="Run local suite", exact=True).click()
    expect(page.locator("#job-status")).to_have_text("Running")
    expect(page.get_by_role("button", name="Cancel run", exact=True)).to_be_visible()
    expect(page.locator("#job-status")).to_have_text("Finished", timeout=120_000)
    expect(page.locator("#console-output")).to_contain_text("42 passed")
    job = client.get("/api/job").json()["job"]
    assert job["exit_code"] == 0
    evidence = client.get(f"/api/runs/{job['run_id']}").json()
    expect(page.locator("#summary-report")).to_have_attribute("href", f"/artifacts/{job['run_id']}/report.html")
    expect(page.locator("#summary-title")).to_contain_text("Local suite")
    expect(page.locator("#metric-total")).to_have_text(str(len(evidence["cases"])))
    expect(page.locator("#metric-pass")).to_have_text(str(evidence["counts"]["PASS"]))
    expect(page.locator("#metric-known")).to_have_text(str(evidence["counts"]["KNOWN FAILURE"]))
    expect(page.locator("#metric-fail")).to_have_text("0")
    page.locator('[data-status="KNOWN FAILURE"]').click()
    expect(page.locator("#case-rows tr")).to_have_count(evidence["counts"]["KNOWN FAILURE"])
    page.locator("#case-search").fill("polling_recovers")
    expect(page.locator("#case-rows tr")).to_have_count(1)
    page.locator("#case-rows .case-name").click()
    expect(page.locator("#case-dialog")).to_be_visible()
    expect(page.locator("#detail-status")).to_have_text("KNOWN FAILURE")
    expect(page.locator("#detail-output")).to_contain_text("OBS06")
    page.keyboard.press("Escape")
    for name, path in evidence["artifacts"].items():
        response = client.get(path)
        assert response.status_code == 200, name
        assert response.content, name
    page.locator("#case-search").fill("")
    page.locator('[data-status="ALL"]').click()
    expect(page.locator("#case-rows tr")).to_have_count(len(evidence["cases"]))
    page.evaluate("window.scrollTo(0, 0)")
    previews = ROOT / "testbench/results/dashboard-preview"
    previews.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(previews / "desktop.png"))
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate("window.scrollTo(0, 0)")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=str(previews / "mobile.png"), full_page=True)
    assert page_errors == []
