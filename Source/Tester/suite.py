# runs the shared test list against one target over HTTP, then builds the suite report

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import httpx

# gives each target call the per-call limit chosen in TT-Q5
CALL_TIMEOUT = 90.0

# reads the change tests' expected answers from one file, so it can be handed to Team 16 as it is
EXPECTED = json.loads((Path(__file__).parent / "expected_changes.json").read_text(encoding="utf-8"))
# lists T-01 to T-07 in order, each with its tag, commit, base and expected answer, or why it is skipped
CHANGE_CASES = EXPECTED["tests"]
# names the pod's fixture repo and the commit the saved-result tests analyse, c1-impl-only (TT-Q8)
FIXTURE_REPO = EXPECTED["repository"]
FIXTURE_COMMIT = next(c["commit"] for c in CHANGE_CASES if c.get("tag") == "c1-impl-only")
# names a repository and a commit no system can find, for T-12 and T-13
MISSING_REPO = "ParthGupta06/no-such-repository"
MISSING_COMMIT = "deadbeef" * 5

# lists the pod contract's 500 error codes, any other 5xx is the system's own failure (TT-Q9), LLM_UNAVAILABLE is ours alone
LISTED_500 = frozenset({"TIMEOUT", "WRITE_FAILED"})

# lists the error sources the tester answers with, a target's other values become unknown
SOURCES = frozenset({"tester", "system", "communication", "unknown"})

# lists the pod's components and acceptance criteria, each covered once an executed test exercises it (TT-Q3)
COMPONENTS = tuple(f"C{n}" for n in range(1, 8))
CRITERIA = tuple(f"AC-{n:02d}" for n in range(1, 11))


class TargetError(Exception):
    # carries a target failure the tester passes back as its own error body

    def __init__(self, status: int, message: str, source: str) -> None:
        super().__init__(message)
        self.status, self.message, self.source = status, message, source


class Result(NamedTuple):
    # judges one test: pass, fail, error or skip, what was expected and what came back, and an error's source
    outcome: str
    message: str
    source: str | None = None


def client() -> httpx.Client:
    # opens the client for every target call, tests swap it for one that reaches an in-process app or a stub
    return httpx.Client(timeout=CALL_TIMEOUT)


def _body(r: httpx.Response):
    # reads a body as JSON, None when it isn't
    try:
        return r.json()
    except ValueError:
        return None


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
    source = body.get("source") if body.get("source") in SOURCES else "unknown"
    # keeps an error status an error, a target's 200 can't become ours
    raise TargetError(r.status_code if r.status_code >= 400 else 500, str(message), source)


# --- the shared test list --------------------------------------------


def _unexpected(r: httpx.Response, expected: str) -> Result:
    # judges an answer other than the expected one, an unlisted 5xx is the system's error and anything else a fail
    body = _body(r)
    code = body.get("code") if isinstance(body, dict) else None
    got = f"{r.status_code} {code or 'without a code'}"
    if r.status_code >= 500 and not (r.status_code == 500 and code in LISTED_500):
        return Result("error", f"expected {expected}, the target failed with {got}", "system")
    return Result("fail", f"expected {expected}, got {got}")


def expect_error(r: httpx.Response, status: int, code: str) -> Result:
    # judges an error test on status, code and a non-empty message, never the message's wording (TT-Q9)
    body = _body(r)
    if r.status_code != status or not isinstance(body, dict) or body.get("code") != code:
        return _unexpected(r, f"{status} {code}")
    message = body.get("message")
    if not isinstance(message, str) or not message.strip():
        return Result("fail", f"expected {status} {code} with a message, got {status} {code} with an empty message")
    return Result("pass", f"answered {status} {code}")


def _analyze(http: httpx.Client, target_url: str, body: dict) -> httpx.Response:
    # posts one analysis request as JSON
    return http.post(f"{target_url}/analyze", json=body)


def t08(http: httpx.Client, target_url: str) -> Result:
    # leaves out commit_id
    return expect_error(_analyze(http, target_url, {"repository": FIXTURE_REPO}), 400, "INVALID_REQUEST")


def t09(http: httpx.Client, target_url: str) -> Result:
    # sends a body that isn't valid JSON
    r = http.post(f"{target_url}/analyze", content=b'{"repository": ', headers={"content-type": "application/json"})
    return expect_error(r, 400, "INVALID_REQUEST")


def t10(http: httpx.Client, target_url: str) -> Result:
    # names a repository that isn't in owner/name form
    r = _analyze(http, target_url, {"repository": "not-a-repo", "commit_id": FIXTURE_COMMIT})
    return expect_error(r, 400, "INVALID_REQUEST")


def t11(http: httpx.Client, target_url: str) -> Result:
    # sends commit_id as a number
    r = _analyze(http, target_url, {"repository": FIXTURE_REPO, "commit_id": 12345})
    return expect_error(r, 400, "INVALID_REQUEST")


def t12(http: httpx.Client, target_url: str) -> Result:
    # names a repository that doesn't exist
    r = _analyze(http, target_url, {"repository": MISSING_REPO, "commit_id": FIXTURE_COMMIT})
    return expect_error(r, 404, "REPOSITORY_NOT_FOUND")


def t13(http: httpx.Client, target_url: str) -> Result:
    # names a commit the fixture repo doesn't have
    r = _analyze(http, target_url, {"repository": FIXTURE_REPO, "commit_id": MISSING_COMMIT})
    return expect_error(r, 404, "COMMIT_NOT_FOUND")


def t15(http: httpx.Client, target_url: str) -> Result:
    # asks for an analysis id no system has saved, passes on 404 ANALYSIS_NOT_FOUND
    r = http.get(f"{target_url}/analysis/an-{uuid.uuid4().hex}")
    return expect_error(r, 404, "ANALYSIS_NOT_FOUND")


# lists the shared contract's enums, DOCUMENTATION included (TT-Q7 row 6)
CHANGE_TYPES = frozenset({"ADDED", "MODIFIED", "DELETED", "RENAMED", "COPIED", "TYPE_CHANGED"})
CATEGORIES = frozenset({"IMPLEMENTATION", "DESIGN", "ARCHITECTURE", "SPECIFICATION", "REQUIREMENT", "DOCUMENTATION", "OTHER"})
FINDING_FIELDS = frozenset(
    {"finding_id", "issue_type", "code_file", "documentation_file", "change_category", "explanation", "verification_status"}
)


def _str(value) -> bool:
    # accepts a string
    return isinstance(value, str)


def _str_or_none(value) -> bool:
    # accepts a string or null
    return value is None or isinstance(value, str)


def _list_of(check: Callable[[object], bool]) -> Callable[[object], bool]:
    # accepts a list whose every item passes check
    return lambda value: isinstance(value, list) and all(check(item) for item in value)


def _change(c) -> bool:
    # accepts one change: path, an optional old_path, and a change type and category from the enums
    return (
        isinstance(c, dict) and _str(c.get("path")) and _str_or_none(c.get("old_path"))
        and c.get("change_type") in CHANGE_TYPES and c.get("category") in CATEGORIES
    )


def _skip(s) -> bool:
    # accepts one skipped file: its path and a reason
    return isinstance(s, dict) and _str(s.get("path")) and _str(s.get("reason"))


def _finding(f) -> bool:
    # accepts one finding with every field, its category from the enum
    return isinstance(f, dict) and FINDING_FIELDS <= set(f) and f["change_category"] in CATEGORIES


def _error_body(e) -> bool:
    # accepts null or an ErrorBody
    return e is None or (isinstance(e, dict) and _str(e.get("code")) and _str(e.get("message")))


# checks each field of the contract's AnalysisResult, the saved-result tests hold every run to it
RESULT_FIELDS = {
    "analysis_id": _str,
    "repository": _str,
    "head_commit": _str,
    "base_commit": _str_or_none,
    "config_version": _str,
    "tool_version": _str,
    "status": lambda v: v in ("SUCCESS", "ERROR"),
    "error": _error_body,
    "issues": _list_of(_finding),
    "changes": _list_of(_change),
    "skipped": _list_of(_skip),
    "created_at": _str,
}
# leaves out the fields that differ between identical runs (Phase 2 §5.1)
PER_RUN = ("analysis_id", "created_at")


def _schema_problem(body: dict) -> str | None:
    # names what breaks the result schema, None when nothing does
    missing = [f for f in RESULT_FIELDS if f not in body]
    if missing:
        return "missing " + ", ".join(missing)
    wrong = [f for f, ok in RESULT_FIELDS.items() if not ok(body[f])]
    return ", ".join(wrong) + " has the wrong type" if wrong else None


def _saved_run(
    http: httpx.Client, target_url: str, commit: str = FIXTURE_COMMIT, base: str | None = None
) -> tuple[dict | None, Result | None]:
    # analyses a fixture commit, against base when given, returns the schema-valid result or the judgement when it isn't one
    request = {"repository": FIXTURE_REPO, "commit_id": commit}
    if base is not None:
        request["base_commit"] = base
    r = _analyze(http, target_url, request)
    body = _body(r)
    if r.status_code != 200 or not isinstance(body, dict):
        return None, _unexpected(r, "200 with a saved result")
    problem = _schema_problem(body)
    if problem:
        return None, Result("fail", f"expected a schema-valid result, got one that breaks the schema: {problem}")
    return body, None


def _saved_runs(http: httpx.Client, target_url: str, count: int) -> tuple[list[dict], Result | None]:
    # analyses the fixture commit count times, stopping at the first run that isn't a schema-valid result
    runs = []
    for _ in range(count):
        posted, failed = _saved_run(http, target_url)
        if failed:
            return runs, failed
        runs.append(posted)
    return runs, None


def _differing(a: dict, b: dict) -> list[str]:
    # lists the fields two bodies disagree on, sorted
    return sorted(k for k in a.keys() | b.keys() if a.get(k) != b.get(k))


def _served_back(http: httpx.Client, target_url: str, posted: dict) -> Result | None:
    # reads a run back by its id, None when it equals the POST body
    path = f"/analysis/{posted['analysis_id']}"
    r = http.get(target_url + path)
    if r.status_code != 200:
        return _unexpected(r, f"200 for GET {path}")
    served = _body(r)
    if served != posted:
        differ = _differing(posted, served) if isinstance(served, dict) else ["the whole body"]
        return Result("fail", f"expected GET {path} to return the POST body, it differs in {', '.join(differ)}")
    return None


def t14(http: httpx.Client, target_url: str) -> Result:
    # analyses once, then reads the run back
    runs, failed = _saved_runs(http, target_url, 1)
    if failed:
        return failed
    return _served_back(http, target_url, runs[0]) or Result("pass", "GET /analysis/{id} returned the POST body")


def t16(http: httpx.Client, target_url: str) -> Result:
    # analyses twice, expects two ids that each read back unchanged
    runs, failed = _saved_runs(http, target_url, 2)
    if failed:
        return failed
    if runs[0]["analysis_id"] == runs[1]["analysis_id"]:
        return Result("fail", f"expected two different ids, got {runs[0]['analysis_id']} twice")
    for posted in runs:
        failed = _served_back(http, target_url, posted)
        if failed:
            return failed
    return Result("pass", "two runs got two ids, both read back unchanged")


def t17(http: httpx.Client, target_url: str) -> Result:
    # analyses five times, expects schema-valid runs equal apart from id and time, tool_version included
    runs, failed = _saved_runs(http, target_url, 5)
    if failed:
        return failed
    kept = [{k: v for k, v in run.items() if k not in PER_RUN} for run in runs]
    differ = sorted({field for run in kept[1:] for field in _differing(kept[0], run)})
    apart = " and ".join(PER_RUN)
    if differ:
        return Result("fail", f"expected five runs equal apart from {apart}, they differ in {', '.join(differ)}")
    return Result("pass", f"five runs agree on every field but {apart}")


class ChangeKey(NamedTuple):
    # holds what TT-Q9 compares of one change
    path: str | None
    old_path: str | None
    change_type: str | None
    category: str | None

    @classmethod
    def of(cls, c: dict) -> ChangeKey:
        # reads the compared fields of a change
        return cls(c.get("path"), c.get("old_path"), c.get("change_type"), c.get("category"))

    def __str__(self) -> str:
        # words a change the way a person reads it, a rename as old -> new
        path = f"{self.old_path} -> {self.path}" if self.old_path else self.path
        return f"{path} {self.change_type} {self.category}"


def _skips(skipped: list[dict]) -> set[tuple[str, str]]:
    # reduces skipped files to (path, reason) pairs
    return {(s["path"], s["reason"]) for s in skipped}


def _show(items: set) -> str:
    # words a set for a message, sorted, as {a, b}
    return "{" + ", ".join(sorted(str(i) if isinstance(i, ChangeKey) else " ".join(i) for i in items)) + "}"


def change_test(case: dict) -> Callable[[httpx.Client, str], Result]:
    # builds one change test from its entry in the data file, sending the base only when the entry says so
    explicit = case.get("explicit_base", False)

    def check(http: httpx.Client, target_url: str) -> Result:
        # compares changes[] as an unordered set, then skipped[] and the base when the case names them
        got, failed = _saved_run(http, target_url, case["commit"], case["base_commit"] if explicit else None)
        if failed:
            return failed
        problems = []
        expected = {ChangeKey.of(c) for c in case["changes"]}
        received = {ChangeKey.of(c) for c in got["changes"]}
        if received != expected:
            problems.append(f"expected changes {_show(expected)}, got {_show(received)}")
        if "skipped" in case:
            want, have = _skips(case["skipped"]), _skips(got["skipped"])
            if have != want:
                problems.append(f"expected skipped {_show(want)}, got {_show(have)}")
        if explicit and got["base_commit"] != case["base_commit"]:
            problems.append(f"expected base_commit {case['base_commit']} ({case['base_tag']}) as sent, got {got['base_commit']}")
        if case["base_commit"] is None:
            if got["base_commit"] is not None:
                problems.append(f"expected base_commit null for a root commit, got {got['base_commit']}")
            if any(c["change_type"] != "ADDED" for c in got["changes"]):
                problems.append("expected every change of a root commit to be ADDED")
        if problems:
            return Result("fail", f"{case['tag']}: " + "; ".join(problems))
        also = f" and skipped {_show(_skips(case['skipped']))}" if "skipped" in case else ""
        return Result("pass", f"{case['tag']}: got the expected changes {_show(expected)}{also}")

    return check


class SharedTest(NamedTuple):
    # defines one shared test: its id, its judge, and the components and criteria it exercises
    test_id: str
    check: Callable[[httpx.Client, str], Result]
    components: list[str]
    criteria: list[str]


# lists the shared tests in the order they run, the change tests' tags come from the data file
TESTS: list[SharedTest] = [
    *(SharedTest(c["test_id"], change_test(c), c["components"], c["criteria"]) for c in CHANGE_CASES),
    SharedTest("T-08", t08, ["C1"], ["AC-07"]),
    SharedTest("T-09", t09, ["C1"], ["AC-07"]),
    SharedTest("T-10", t10, ["C1"], ["AC-07"]),
    SharedTest("T-11", t11, ["C1"], ["AC-07"]),
    SharedTest("T-12", t12, ["C1", "C2"], ["AC-08"]),
    SharedTest("T-13", t13, ["C1", "C2"], ["AC-08"]),
    SharedTest("T-14", t14, ["C1", "C2", "C3", "C5", "C6"], ["AC-06"]),
    SharedTest("T-15", t15, ["C1", "C6"], ["AC-06"]),
    SharedTest("T-16", t16, ["C1", "C2", "C3", "C5", "C6"], ["AC-06"]),
    SharedTest("T-17", t17, ["C1", "C2", "C3", "C5"], ["AC-10"]),
]


def _run_one(http: httpx.Client, target_url: str, test: SharedTest) -> dict:
    # runs one test, a call with no answer is an error from communication
    try:
        result = test.check(http, target_url)
    except httpx.TransportError as exc:
        result = Result("error", f"the target gave no answer: {exc}", "communication")
    found = {"test_id": test.test_id, "outcome": result.outcome, "message": result.message}
    if result.source is not None:
        found["source"] = result.source
    return found


# --- coverage --------------------------------------------------------


def _uncounted(basis: str) -> dict:
    # reports a count the tester can't give, null and never zero
    return {"covered": None, "total": None, "basis": basis}


def code_coverage(http: httpx.Client, target_url: str, session_id: str) -> dict:
    # copies coverage.code from the target's report, null counts with the reason when it can't
    try:
        r = http.get(f"{target_url}/test/report", params={"session_id": session_id})
    except httpx.TransportError as exc:
        return _uncounted(f"the target's /test/report gave no answer: {exc}")
    if r.status_code != 200:
        return _uncounted(f"the target's /test/report answered {r.status_code}")
    body = _body(r)
    coverage = body.get("coverage") if isinstance(body, dict) else None
    code = coverage.get("code") if isinstance(coverage, dict) else None
    # copies a code count only when it has both numbers, a partial one would read as a real count
    if not isinstance(code, dict) or not {"covered", "total"} <= set(code):
        return _uncounted("the target's /test/report has no coverage.code with covered and total")
    return code


def _counted(listed: tuple[str, ...], covered: set[str], what: str) -> dict:
    # reports how many of a pod list the executed tests exercised, naming them in Team 16's wording
    found = [i for i in listed if i in covered]
    names = ", ".join(found) or "none"
    basis = f"{what} {listed[0]}-{listed[-1]} listed in the pod specification exercised by at least one executed test: {names}"
    return {"covered": len(found), "total": len(listed), "basis": basis}


def tag_coverage(results: list[dict]) -> dict:
    # counts component and system coverage from the tags of every test that ran, a skipped test covers nothing
    ran = {r["test_id"] for r in results if r["outcome"] != "skip"}
    executed = [t for t in TESTS if t.test_id in ran]
    return {
        "component": _counted(COMPONENTS, {c for t in executed for c in t.components}, "Components"),
        "system": _counted(CRITERIA, {c for t in executed for c in t.criteria}, "Acceptance criteria"),
    }


def run(session_id: str, target_url: str) -> dict:
    # runs every shared test once, then reads the target's report, in the suite report's field order
    with client() as http:
        results = [_run_one(http, target_url, test) for test in TESTS]
        code = code_coverage(http, target_url, session_id)
    return {
        "session_id": session_id,
        "target_url": target_url,
        "results": results,
        "coverage": {"code": code, **tag_coverage(results)},
    }
