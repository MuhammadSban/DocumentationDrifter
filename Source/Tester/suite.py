# runs the shared test list against one target over HTTP, then builds the suite report

from __future__ import annotations

import uuid
from collections.abc import Callable

import httpx

# gives each target call the per-call limit chosen in TT-Q5
CALL_TIMEOUT = 90.0

# words the coverage kinds ticket 04 will count, null until the tests carry their tags
NOT_COUNTED = {
    "component": "Not counted yet: the shared tests don't carry their component tags (C1 to C7)",
    "system": "Not counted yet: the shared tests don't carry their acceptance-criteria tags (AC-01 to AC-10)",
}


class TargetError(Exception):
    # carries a target failure the tester passes back as its own error body

    def __init__(self, status: int, message: str, source: str) -> None:
        super().__init__(message)
        self.status, self.message, self.source = status, message, source


def client() -> httpx.Client:
    # opens the client for every target call, tests swap it for one that reaches an in-process app or a stub
    return httpx.Client(timeout=CALL_TIMEOUT)


def setup_target(target_url: str, session_id: str) -> None:
    # opens the session on the target, raises TargetError unless the target answers 201
    try:
        with client() as http:
            r = http.post(f"{target_url}/test/setup", json={"session_id": session_id, "setup": {}})
    except (httpx.InvalidURL, ValueError) as exc:
        raise TargetError(400, f"target_url {target_url} is not a valid URL: {exc}", "tester") from exc
    except httpx.TransportError as exc:
        raise TargetError(500, f"target setup at {target_url} got no answer: {exc}", "communication") from exc
    if r.status_code == 201:
        return
    body = _body(r)
    body = body if isinstance(body, dict) else {}
    message = body.get("message") or f"target setup answered {r.status_code}, expected 201"
    source = body.get("source") or "unknown"
    # keeps an error status an error, a target's 200 can't become ours
    raise TargetError(r.status_code if r.status_code >= 400 else 500, str(message), str(source))


# --- the shared test list --------------------------------------------


def _body(r: httpx.Response):
    # reads a body as JSON, None when it isn't
    try:
        return r.json()
    except ValueError:
        return None


def expect_error(r: httpx.Response, status: int, code: str) -> tuple[str, str, str | None]:
    # judges an error test on status and code alone, never the message's wording (TT-Q9)
    if r.status_code >= 500 and status < 500:
        return "error", f"expected {status} {code}, the target failed with {r.status_code}", "system"
    body = _body(r)
    got = body.get("code") if isinstance(body, dict) else None
    if r.status_code == status and got == code:
        return "pass", f"answered {status} {code}", None
    return "fail", f"expected {status} {code}, got {r.status_code} {got or 'without a code'}", None


def t15(http: httpx.Client, target_url: str) -> tuple[str, str, str | None]:
    # asks for an analysis id no system has saved, passes on 404 ANALYSIS_NOT_FOUND
    r = http.get(f"{target_url}/analysis/an-{uuid.uuid4().hex}")
    return expect_error(r, 404, "ANALYSIS_NOT_FOUND")


# lists the shared tests in the order they run, each judged by its function
TESTS: list[tuple[str, Callable[[httpx.Client, str], tuple[str, str, str | None]]]] = [
    ("T-15", t15),
]


def _run_one(http: httpx.Client, target_url: str, test_id: str, check) -> dict:
    # runs one test, a call with no answer is an error from communication
    try:
        outcome, message, source = check(http, target_url)
    except httpx.TransportError as exc:
        outcome, message, source = "error", f"the target gave no answer: {exc}", "communication"
    result = {"test_id": test_id, "outcome": outcome, "message": message}
    if source is not None:
        result["source"] = source
    return result


# --- coverage --------------------------------------------------------


def _unknown(basis: str) -> dict:
    # reports a count the tester can't give, null and never zero
    return {"covered": None, "total": None, "basis": basis}


def code_coverage(http: httpx.Client, target_url: str, session_id: str) -> dict:
    # copies coverage.code from the target's report, null counts with the reason when it can't
    try:
        r = http.get(f"{target_url}/test/report", params={"session_id": session_id})
    except httpx.TransportError as exc:
        return _unknown(f"the target's /test/report gave no answer: {exc}")
    if r.status_code != 200:
        return _unknown(f"the target's /test/report answered {r.status_code}")
    body = _body(r)
    coverage = body.get("coverage") if isinstance(body, dict) else None
    code = coverage.get("code") if isinstance(coverage, dict) else None
    # copies a code count only when it has both numbers, a partial one would read as a real count
    if not isinstance(code, dict) or not {"covered", "total"} <= set(code):
        return _unknown("the target's /test/report has no coverage.code with covered and total")
    return code


def run(session_id: str, target_url: str) -> dict:
    # runs every shared test once, then reads the target's report, in the suite report's field order
    with client() as http:
        results = [_run_one(http, target_url, test_id, check) for test_id, check in TESTS]
        code = code_coverage(http, target_url, session_id)
    return {
        "session_id": session_id,
        "target_url": target_url,
        "results": results,
        "coverage": {"code": code, **{kind: _unknown(basis) for kind, basis in NOT_COUNTED.items()}},
    }
