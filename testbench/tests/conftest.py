# starts the real API and console for website tests, or targets configured URLs

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]


def pytest_addoption(parser):
    # accepts a Railway API URL and an optional separately hosted console
    group = parser.getgroup("DocumentationDrifter website")
    group.addoption("--website-url", default=os.environ.get("DRIFTER_TARGET_URL", ""), help="API origin or URL ending in /system; empty starts locally")
    group.addoption("--console-url", default=os.environ.get("DRIFTER_CONSOLE_URL", ""), help="Console page URL; empty serves Source/Frontend locally")


def pytest_configure(config):
    # identifies website checks independently of the existing GitHub network marker
    config.addinivalue_line("markers", "website: tests the DocumentationDrifter HTTP service or console")
    # keeps Playwright's session cleanup away from JUnit files in the parent folder
    if getattr(config.option, "output", None) == "test-results":
        config.option.output = str(ROOT / "testbench/results/browser")


def _url(value: str) -> str:
    # rejects a mistyped target before issuing any requests
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
        raise pytest.UsageError("Website URLs must be http(s) URLs without a query or fragment")
    return value.rstrip("/")


@contextmanager
def _server(command, folder, ready_path, env=None):
    # runs one owned server process and closes it even when a test fails
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    with (folder / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [*command, "--port", str(port)], cwd=ROOT, env=env,
            stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            with httpx.Client(timeout=1, trust_env=False) as client:
                until = time.monotonic() + 15
                while time.monotonic() < until and process.poll() is None:
                    try:
                        if client.get(url + ready_path).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    pytest.fail(f"Server did not start; see {folder / 'server.log'}")
            yield url
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


@pytest.fixture(scope="session")
def built(tmp_path_factory):
    # builds the shared labelled repository without importing the original suite's conftest
    sys.path.insert(0, str(ROOT / "tools"))
    import testrepo

    root = tmp_path_factory.mktemp("testbench-fixtures")
    bare = root / "fixtures/drifter-testrepo.git"
    manifest = testrepo.build(bare)
    return root, bare, manifest


@pytest.fixture(scope="session")
def website_url(pytestconfig, tmp_path_factory, request):
    # serves the real application with a local fixture remote when no target is supplied
    target = pytestconfig.getoption("--website-url")
    if target:
        target = _url(target)
        yield target.removesuffix("/system")
        return
    root, _, _ = request.getfixturevalue("built")
    folder = tmp_path_factory.mktemp("website-api")
    env = {**os.environ, "DRIFTER_REMOTE_BASE_URL": root.as_uri() + "/", "DRIFTER_RUNS_DIR": str(folder / "runs"), "DRIFTER_CLONE_DIR": str(folder / "clones")}
    command = [sys.executable, "-m", "uvicorn", "--app-dir", str(ROOT / "Source"), "testbench.local_app:create_app", "--factory", "--host", "127.0.0.1"]
    with _server(command, folder, "/system/health", env) as url:
        yield url


@pytest.fixture(scope="session")
def website_client(website_url):
    # warms a sleeping host once and keeps all API tests on that actual HTTP target
    with httpx.Client(base_url=website_url + "/", timeout=180, follow_redirects=True) as client:
        until = time.monotonic() + 90
        while True:
            try:
                response = client.get("system/health", timeout=5)
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() >= until:
                pytest.fail(f"{website_url}/system/health did not become ready within 90 seconds")
            time.sleep(0.25)
        yield client


@pytest.fixture(scope="session")
def website_cases(pytestconfig, built):
    # uses the same labelled cases locally and on the published public test repo
    if pytestconfig.getoption("--website-url"):
        import testrepo

        repository = os.environ.get("DRIFTER_TEST_REPO", testrepo.PUBLIC_REPO)
        if not repository:
            raise pytest.UsageError("DRIFTER_TEST_REPO must name the published fixture repository for hosted analysis tests")
    else:
        repository = built[1].relative_to(built[0]).as_posix().removesuffix(".git")
    return repository, built[2]["labels"]


@pytest.fixture(scope="session")
def console_url(pytestconfig, website_url, tmp_path_factory):
    # proxies the local console to the selected API unless a console URL is supplied
    target = pytestconfig.getoption("--console-url")
    if target:
        yield _url(target)
        return
    folder = tmp_path_factory.mktemp("website-console")
    command = [sys.executable, str(ROOT / "Source/Frontend/ui.py"), "--api", website_url]
    with _server(command, folder, "/") as url:
        yield url
