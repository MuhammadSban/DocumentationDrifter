# covers ticket 08: TIMEOUT, the concurrency cap and WRITE_FAILED, plus the slot wait cap and INTERNAL_ERROR

import sys
import threading
import time
from pathlib import Path

import pytest


def configure(monkeypatch, **values):
    # sets DRIFTER_* values and drops the cached settings
    for key, value in values.items():
        monkeypatch.setenv(f"DRIFTER_{key.upper()}", str(value))
    from GitHub_Connector.settings import get_settings

    get_settings.cache_clear()


def analyse(api, head):
    # posts one analysis request and returns the response
    return api.post("/system/analyze", json={"repository": "octo/demo", "commit_id": head})


@pytest.fixture
def head(make_repo):
    # builds a small repo and returns its head commit
    repo = make_repo()
    repo.commit({"a.txt": "1\n"})
    return repo.commit({"b.txt": "2\n"})


def assert_failed(r, code, env):
    # checks a 500 ErrorBody that saved nothing and left no clone
    assert r.status_code == 500, r.text
    assert r.json()["code"] == code and r.json()["message"]
    assert not any(env["runs"].iterdir()) if env["runs"].is_dir() else True
    assert list(env["clones"].iterdir()) == []


def stray_git(clones: Path) -> list[str]:
    # finds git processes still working inside the clone folder (Linux only)
    found = []
    for cmdline in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            text = cmdline.read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        if "git" in text and str(clones) in text:
            found.append(text)
    return found


def test_defaults():
    from GitHub_Connector.settings import AnalysisSettings

    s = AnalysisSettings()
    assert (s.git_timeout, s.analysis_deadline, s.max_concurrent, s.slot_wait) == (60, 120, 2, 120)


def test_tiny_deadline_gives_timeout(api, head, v1_env, monkeypatch):
    configure(monkeypatch, analysis_deadline=0.000001)
    r = analyse(api, head)
    assert_failed(r, "TIMEOUT", v1_env)
    assert "took longer than" in r.json()["message"]


def test_tiny_git_timeout_gives_timeout_and_stops_git(api, head, v1_env, monkeypatch):
    configure(monkeypatch, git_timeout=0.001)
    assert_failed(analyse(api, head), "TIMEOUT", v1_env)
    if sys.platform.startswith("linux"):
        time.sleep(0.2)
        assert stray_git(v1_env["clones"]) == []


def test_extra_requests_wait_for_a_slot_and_waiting_is_not_counted(api, head, v1_env, monkeypatch):
    configure(monkeypatch, max_concurrent=1, analysis_deadline=2)
    from GitHub_Connector.analysis import slot

    results = []
    with slot():
        worker = threading.Thread(target=lambda: results.append(analyse(api, head)))
        worker.start()
        time.sleep(2.5)  # waits past the deadline, the queued request must still succeed
        assert results == [], "the request ran without a free slot"
    worker.join(timeout=30)
    assert results[0].status_code == 200, results[0].text


def test_two_simultaneous_requests_both_succeed_with_one_slot(api, head, monkeypatch):
    configure(monkeypatch, max_concurrent=1)
    results = []
    threads = [threading.Thread(target=lambda: results.append(analyse(api, head))) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert [r.status_code for r in results] == [200, 200]


def test_unwritable_run_store_gives_write_failed(api, head, v1_env, monkeypatch, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where the run store folder should be")
    configure(monkeypatch, runs_dir=blocker / "runs")
    r = analyse(api, head)
    assert r.status_code == 500
    assert r.json()["code"] == "WRITE_FAILED"
    assert list(v1_env["clones"].iterdir()) == []
    assert blocker.read_text().startswith("a file")


def test_success_always_means_the_run_can_be_fetched(api, head):
    r = analyse(api, head)
    assert r.status_code == 200
    assert api.get(f"/system/analysis/{r.json()['analysis_id']}").content == r.content


def test_no_free_slot_gives_timeout_instead_of_hanging(api, head, v1_env, monkeypatch):
    configure(monkeypatch, max_concurrent=1, slot_wait=0.2)
    from GitHub_Connector.analysis import slot

    with slot():
        r = analyse(api, head)
    assert_failed(r, "TIMEOUT", v1_env)
    assert "slot" in r.json()["message"]
    assert analyse(api, head).status_code == 200, "the slot must be free again"


@pytest.fixture
def lenient_api(v1_env):
    # builds a test client that returns the 500 response instead of re-raising the server's exception
    from fastapi.testclient import TestClient

    from GitHub_Connector.api import app

    return TestClient(app, raise_server_exceptions=False)


def test_unforeseen_git_failure_gives_internal_error(lenient_api, head, v1_env, monkeypatch):
    import subprocess

    from GitHub_Connector import analysis

    def broken(*args, **kwargs):
        raise subprocess.CalledProcessError(128, ["git", "fetch"], b"", b"fatal: unexpected")

    monkeypatch.setattr(analysis, "fetch", broken)
    r = analyse(lenient_api, head)
    assert_failed(r, "INTERNAL_ERROR", v1_env)
    assert r.headers["content-type"] == "application/json"


def test_unreadable_saved_run_gives_internal_error(lenient_api, monkeypatch):
    from GitHub_Connector import runs

    def broken(analysis_id):
        raise PermissionError("run file unreadable")

    monkeypatch.setattr(runs, "load", broken)
    r = lenient_api.get("/system/analysis/an-" + "0" * 32)
    assert r.status_code == 500
    assert r.json() == {"code": "INTERNAL_ERROR", "message": "the request failed unexpectedly"}
