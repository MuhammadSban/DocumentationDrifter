# helps the tester tests: the target URLs, the tester calls, and a stub target that behaves like a correct system

from __future__ import annotations

import json
import uuid

import httpx

SYSTEM = "http://testserver/system"
STUB = "http://stub.test/system"


def setup(api, target_url=SYSTEM):
    # opens a tester session against target_url
    return api.post("/tester/test/setup", json={"target_url": target_url})


def run(api, session_id):
    # runs the suite on an open session
    return api.post("/tester/test/run", json={"session_id": session_id})


def assert_error(r, status, source):
    # checks the tester's error body, a non-empty message and the given source
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) == {"message", "source"} and body["message"] and body["source"] == source


def results(body: dict) -> dict[str, dict]:
    # indexes a suite report's results by test id
    return {r["test_id"]: r for r in body["results"]}


def _error(status: int, code: str, message: str = "stub says no") -> httpx.Response:
    # answers with the contract's ErrorBody
    return httpx.Response(status, json={"code": code, "message": message})


# describes the one change every stub run reports
CHANGE = {"path": "src/model.py", "old_path": None, "change_type": "MODIFIED", "category": "IMPLEMENTATION"}


def analysis(request_body: dict) -> dict:
    # builds a result shaped like the contract's, the same apart from analysis_id and created_at
    return {
        "analysis_id": f"an-{uuid.uuid4().hex}",
        "repository": request_body["repository"],
        "head_commit": request_body["commit_id"],
        "base_commit": None,
        "config_version": "stub",
        "tool_version": "stub-1",
        "status": "SUCCESS",
        "error": None,
        "issues": [],
        "changes": [CHANGE],
        "skipped": [],
        "created_at": f"2026-10-18T00:00:{uuid.uuid4().int % 60:02d}.000Z",
    }


def healthy(routes) -> dict:
    # fills a stub with a target that answers every shared test correctly, returns its saved runs by id
    from Tester import suite

    saved: dict = {}

    def analyze(request: httpx.Request) -> httpx.Response:
        try:
            body = json.loads(request.content)
        except ValueError:
            return _error(400, "INVALID_REQUEST")
        repo, commit = body.get("repository"), body.get("commit_id")
        if not isinstance(repo, str) or not isinstance(commit, str) or "/" not in repo:
            return _error(400, "INVALID_REQUEST")
        if repo != suite.FIXTURE_REPO:
            return _error(404, "REPOSITORY_NOT_FOUND")
        if commit != suite.FIXTURE_COMMIT:
            return _error(404, "COMMIT_NOT_FOUND")
        result = analysis(body)
        saved[result["analysis_id"]] = result
        return httpx.Response(200, json=result)

    def get_analysis(request: httpx.Request) -> httpx.Response:
        found = saved.get(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, json=found) if found else _error(404, "ANALYSIS_NOT_FOUND")

    routes[("POST", "/test/setup")] = lambda r: httpx.Response(201, json={"session_id": json.loads(r.content)["session_id"]})
    routes[("POST", "/analyze")] = analyze
    routes[("GET", "/analysis/*")] = get_analysis
    code = {"covered": 3, "total": 10, "basis": "stub lines"}
    routes[("GET", "/test/report")] = lambda r: httpx.Response(
        200, json={"session_id": r.url.params["session_id"], "coverage": {"code": code}}
    )
    return saved


def rewrite(routes, key: tuple[str, str], transform):
    # wraps one stub route so each 200 body passes through transform(body, n), n counting from 1, other answers unchanged
    answer = routes[key]
    count = {"n": 0}

    def rewritten(request):
        r = answer(request)
        if r.status_code != 200:
            return r
        count["n"] += 1
        return httpx.Response(200, json=transform(r.json(), count["n"]))

    routes[key] = rewritten
