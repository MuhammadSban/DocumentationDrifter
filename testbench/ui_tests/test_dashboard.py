# verifies dashboard run control, evidence access and request validation without external services

import json
import time

import pytest
from fastapi.testclient import TestClient

from testbench.serve_testbench import Bench, create_app

RUN_ID = "20261018-120000-000001-local"


@pytest.fixture
def dashboard(tmp_path):
    # supplies a short controlled runner to exercise actual subprocess ownership
    runner = tmp_path / "testbench/run_testbench.py"
    runner.parent.mkdir()
    runner.write_text('''import json, sys, time
from pathlib import Path
folder = Path(__file__).parent / "results/bench/20261018-120000-000001-local"
print("Evidence folder: " + str(folder.resolve()), flush=True)
print("controlled runner output", flush=True)
time.sleep(30 if "live" in sys.argv else 0.2)
folder.mkdir(parents=True)
data = {"mode": "local", "exit_code": 0, "counts": {"PASS": 1}, "cases": [{"name": "fixture_case", "status": "PASS"}]}
(folder / "summary.json").write_text(json.dumps(data))
(folder / "report.html").write_text("<h1>Fixture report</h1>")
''', encoding="utf-8")
    bench = Bench(tmp_path)
    with TestClient(create_app(bench)) as client:
        yield client, bench


def finished(client):
    # waits for a state transition rather than guessing a fixed completion delay
    until = time.monotonic() + 5
    while time.monotonic() < until:
        data = client.get("/api/job").json()
        if data["job"]["status"] != "running":
            return data
        time.sleep(0.02)
    pytest.fail("The controlled dashboard job did not finish")


def test_dashboard_serves_its_own_page_and_empty_history(dashboard):
    client, _ = dashboard
    assert "Website test bench" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200
    assert client.get("/api/runs").json() == {"runs": []}
    assert client.get("/api/job").json()["job"] is None


@pytest.mark.parametrize("payload", [
    {"mode": "shell"},
    {"mode": "smoke", "url": "file:///etc/passwd"},
    {"mode": "live", "url": "https://user:secret@example.com"},
    {"mode": "smoke", "show_known_failures": True},
    {"mode": "local", "console_url": "https://example.com"},
    {"mode": "live", "url": ""},
    {"mode": "local", "command": "arbitrary command"},
])
def test_invalid_run_options_never_start_a_process(dashboard, payload):
    client, bench = dashboard
    assert client.post("/api/runs", json=payload).status_code == 422
    assert bench.process is None


def test_foreign_browser_origins_cannot_start_runs(dashboard):
    client, bench = dashboard
    assert client.post("/api/runs", json={"mode": "local"}, headers={"Origin": "https://example.com"}).status_code == 403
    assert bench.process is None


def test_run_captures_output_and_exposes_recorded_evidence(dashboard):
    client, _ = dashboard
    response = client.post("/api/runs", json={"mode": "local"}, headers={"Origin": "http://testserver"})
    assert response.status_code == 202
    data = finished(client)
    assert data["job"]["status"] == "completed"
    assert data["job"]["exit_code"] == 0
    assert data["job"]["run_id"] == RUN_ID
    assert "controlled runner output" in data["log"]
    assert client.get(f"/api/job?offset={data['offset']}").json()["log"] == ""
    history = client.get("/api/runs").json()["runs"]
    assert history[0]["case_count"] == 1
    evidence = client.get(f"/api/runs/{RUN_ID}").json()
    assert evidence["cases"][0]["name"] == "fixture_case"
    assert "Fixture report" in client.get(evidence["artifacts"]["report.html"]).text


def test_overlapping_runs_are_rejected_and_cancel_is_not_a_pass(dashboard):
    client, _ = dashboard
    assert client.post("/api/runs", json={"mode": "live"}).status_code == 202
    assert client.post("/api/runs", json={"mode": "local"}).status_code == 409
    assert client.post("/api/job/cancel").status_code == 200
    data = finished(client)
    assert data["job"]["status"] == "cancelled"
    assert data["job"]["exit_code"] != 0
    assert client.get("/api/runs").json()["runs"] == []


def test_history_ignores_incomplete_runs_and_does_not_read_workspace_paths(dashboard, tmp_path):
    client, bench = dashboard
    bad = bench.results / RUN_ID
    bad.mkdir()
    (bad / "summary.json").write_text("broken JSON")
    (tmp_path / "private.txt").write_text("workspace-only content")
    assert client.get("/api/runs").json()["runs"] == []
    assert client.get(f"/api/runs/{RUN_ID}").status_code == 404
    assert client.get("/api/runs/..%2F..%2Fprivate.txt").status_code == 404
    response = client.get("/artifacts/%2e%2e/%2e%2e/private.txt")
    assert response.status_code == 404
    assert "workspace-only content" not in response.text
