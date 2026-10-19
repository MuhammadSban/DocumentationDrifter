# covers ticket 08: TIMEOUT, the concurrency cap and WRITE_FAILED

import os
import shlex
import socketserver
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


@pytest.fixture
def silent_remote():
    # accepts git's HTTP request, then holds the connection open until cleanup
    received = threading.Event()
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            received.set()
            release.wait()

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/", received, release
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def escaped_remote(monkeypatch, tmp_path):
    # hold a detached helper's connection, keeping git's output pipe open until cleanup
    received = threading.Event()
    release = threading.Event()

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            received.set()
            release.wait()
            try:
                self.request.sendall(b"x")
            except OSError:
                pass

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
    helpers = tmp_path / "helpers"
    helpers.mkdir()
    script = helpers / "escaped_output.py"
    script.write_text(
        """import os
import socket
import subprocess
import sys
import time
from pathlib import Path

mode, port = sys.argv[1:]
if mode == "sleeper":
    with socket.create_connection(("127.0.0.1", int(port)), timeout=5) as connection:
        connection.settimeout(None)
        connection.recv(1)
elif mode == "launcher":
    group = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt" else {"start_new_session": True}
    )
    subprocess.Popen(
        [sys.executable, __file__, "sleeper", port],
        cwd=Path(__file__).parent, stdin=subprocess.DEVNULL,
        stdout=sys.stdout, stderr=sys.stderr, **group,
    )
else:
    subprocess.run([sys.executable, __file__, "launcher", port], check=True)
    time.sleep(30)
""",
        encoding="utf-8",
    )
    helper = helpers / "git-remote-drifterhang"
    helper.write_text(
        f"#!/bin/sh\ncd {shlex.quote(helpers.as_posix())} || exit 1\n"
        f"exec {shlex.quote(Path(sys.executable).as_posix())} "
        f"{shlex.quote(script.as_posix())} clone {server.server_address[1]}\n",
        encoding="utf-8",
        newline="\n",
    )
    helper.chmod(0o755)
    monkeypatch.setenv("PATH", str(helpers) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "drifterhang:file")
    thread.start()
    try:
        yield "drifterhang::", received, release
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


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
    assert (s.git_timeout, s.analysis_deadline, s.max_concurrent) == (60, 120, 2)


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


@pytest.mark.parametrize(
    "git_timeout, analysis_deadline",
    [(0.2, 2), (2, 0.2)],
    ids=["git-timeout", "analysis-deadline"],
)
def test_silent_remote_times_out_and_frees_its_slot(
    api, head, v1_env, monkeypatch, silent_remote, git_timeout, analysis_deadline
):
    remote_url, received, release = silent_remote
    session = api.post("/system/test/setup", json={"session_id": f"silent-{time.monotonic_ns()}"})
    assert session.status_code == 201, session.text
    configure(
        monkeypatch,
        remote_base_url=remote_url,
        git_timeout=git_timeout,
        analysis_deadline=analysis_deadline,
        max_concurrent=1,
    )
    results = []
    worker = threading.Thread(target=lambda: results.append(analyse(api, head)), daemon=True)
    worker.start()
    try:
        assert received.wait(timeout=2), "git did not reach the silent remote"
        worker.join(timeout=2)
        assert not worker.is_alive(), "the analysis kept waiting on a silent remote"
        assert_failed(results[0], "TIMEOUT", v1_env)
    finally:
        release.set()
        worker.join(timeout=5)

    configure(
        monkeypatch,
        remote_base_url=v1_env["remotes"].as_uri() + "/",
        git_timeout=30,
        analysis_deadline=30,
    )
    response = analyse(api, head)
    assert response.status_code == 200, response.text


def test_timeout_does_not_wait_for_an_escaped_childs_output(
    api, head, v1_env, monkeypatch, escaped_remote
):
    remote_url, received, release = escaped_remote
    configure(
        monkeypatch,
        remote_base_url=remote_url,
        git_timeout=1,
        analysis_deadline=4,
        max_concurrent=1,
    )
    session = api.post("/system/test/setup", json={"session_id": f"escaped-{time.monotonic_ns()}"})
    assert session.status_code == 201, session.text
    results = []
    worker = threading.Thread(target=lambda: results.append(analyse(api, head)), daemon=True)
    worker.start()
    try:
        assert received.wait(timeout=2), "git did not reach the custom remote helper"
        worker.join(timeout=2.5)
        assert not worker.is_alive(), "timeout kept draining the escaped child's output pipe"
        assert_failed(results[0], "TIMEOUT", v1_env)
    finally:
        release.set()
        worker.join(timeout=5)

    configure(
        monkeypatch,
        remote_base_url=v1_env["remotes"].as_uri() + "/",
        git_timeout=30,
        analysis_deadline=30,
    )
    response = analyse(api, head)
    assert response.status_code == 200, response.text


def test_waiting_for_a_slot_counts_towards_the_deadline(api, head, v1_env, monkeypatch):
    configure(monkeypatch, max_concurrent=1, analysis_deadline=0.2)
    from GitHub_Connector.analysis import slot

    results = []
    worker = threading.Thread(target=lambda: results.append(analyse(api, head)), daemon=True)
    try:
        with slot():
            worker.start()
            worker.join(timeout=2)
            assert not worker.is_alive(), "the queued request waited beyond its deadline"
            assert_failed(results[0], "TIMEOUT", v1_env)
    finally:
        worker.join(timeout=30)

    configure(monkeypatch, analysis_deadline=30)
    response = analyse(api, head)
    assert response.status_code == 200, response.text


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
