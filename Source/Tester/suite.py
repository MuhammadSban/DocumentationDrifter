# runs the shared test list against one target over HTTP, then builds the suite report
# copies Team 16's tester (ParthGupta06/doc-tracker, doctracker/tester/suite.py at 0db21ca): they agree only to what it checks

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import httpx

# gives each target call and the whole suite the limits chosen in TT-Q5, in seconds
CALL_TIMEOUT = float(os.environ.get("TESTER_CALL_TIMEOUT", "90"))
SUITE_TIMEOUT = float(os.environ.get("TESTER_SUITE_TIMEOUT", "600"))

# reads the fixture commits and the change tests' expected answers from one file, so it can be handed to Team 16 as it is
EXPECTED = json.loads((Path(__file__).parent / "expected_changes.json").read_text(encoding="utf-8"))
# names the pod's fixture repo and its commits by tag (TT-Q8), the same SHAs as Team 16's commits.json
FIXTURE_REPO = EXPECTED["repository"]
COMMITS: dict[str, str] = EXPECTED["commits"]
FIXTURE_COMMIT = COMMITS["c1-impl-only"]
# names the requests Team 16's T-10, T-12, T-13 and T-15 send
BAD_REPOSITORY = "not a repo"
MISSING_REPO = "pod15-16-nonexistent/does-not-exist-7f3a"
MISSING_COMMIT = "0" * 40
UNKNOWN_ANALYSIS = "an-" + "0" * 32


def _resolved(case: dict) -> dict:
    # adds a case's commit and base by SHA, base_commit None for a root commit and absent when the case doesn't name one
    found = {**case, "commit": COMMITS[case["tag"]]}
    if case.get("root"):
        found["base_commit"] = None
    elif "base_tag" in case:
        found["base_commit"] = COMMITS[case["base_tag"]]
    return found


# lists T-01 to T-07 in order, each with its tags, commit, base and expected answer
CHANGE_CASES = [_resolved(c) for c in EXPECTED["tests"]]

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
    # holds one test's verdict: pass, fail, error or skip, what was expected and what came back, and an error's source
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


def _got(r: httpx.Response) -> str:
    # words an answer for a message: its status and error code
    body = _body(r)
    code = body.get("code") if isinstance(body, dict) else None
    return f"{r.status_code} {code or 'without a code'}"


def expect_error(r: httpx.Response, status: int, code: str) -> Result:
    # judges an error test on status, code and a non-empty message, never the wording, any 5xx is the system's error
    if r.status_code >= 500:
        return Result("error", f"expected {status} {code}, the target failed with {_got(r)}", "system")
    body = _body(r)
    if r.status_code != status or not isinstance(body, dict) or body.get("code") != code:
        return Result("fail", f"expected {status} {code}, got {_got(r)}")
    if not body.get("message"):
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
    r = http.post(f"{target_url}/analyze", content=b'{"repository": "x/y", "commit_id": ', headers={"content-type": "application/json"})
    return expect_error(r, 400, "INVALID_REQUEST")


def t10(http: httpx.Client, target_url: str) -> Result:
    # names a repository that isn't in owner/name form
    r = _analyze(http, target_url, {"repository": BAD_REPOSITORY, "commit_id": FIXTURE_COMMIT})
    return expect_error(r, 400, "INVALID_REQUEST")


def t11(http: httpx.Client, target_url: str) -> Result:
    # sends commit_id as a number
    r = _analyze(http, target_url, {"repository": FIXTURE_REPO, "commit_id": 12345678})
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
    return expect_error(http.get(f"{target_url}/analysis/{UNKNOWN_ANALYSIS}"), 404, "ANALYSIS_NOT_FOUND")


# checks the top-level fields Team 16's tester checks, by type, the others may be absent
RESULT_FIELDS = {
    "analysis_id": str, "repository": str, "head_commit": str, "config_version": str,
    "tool_version": str, "status": str, "issues": list, "changes": list, "skipped": list,
}
# names the fields T-17 compares across runs, issues are compared apart from finding_id
SIGNIFICANT = ("repository", "head_commit", "base_commit", "status", "changes", "skipped")


def _schema_problem(body: dict) -> str | None:
    # names what breaks Team 16's result check, None when nothing does
    for name, kind in RESULT_FIELDS.items():
        if not isinstance(body.get(name), kind):
            return f"{name} missing or not {kind.__name__}"
    if body["status"] not in ("SUCCESS", "ERROR"):
        return f"status {body['status']!r} is not SUCCESS or ERROR"
    for change in body["changes"]:
        if not isinstance(change, dict) or not all(isinstance(change.get(k), str) for k in ("path", "change_type", "category")):
            return "a change lacks a string path, change_type or category"
    for issue in body["issues"]:
        if not isinstance(issue, dict) or issue.get("verification_status") != "PENDING_REVIEW":
            return "a new finding is not PENDING_REVIEW"
    return None


def _saved_run(
    http: httpx.Client, target_url: str, commit: str = FIXTURE_COMMIT, base: str | None = None
) -> tuple[dict | None, Result | None]:
    # analyses a fixture commit, against base when given, returns a schema-valid SUCCESS result or the judgement when it isn't one
    request = {"repository": FIXTURE_REPO, "commit_id": commit}
    if base is not None:
        request["base_commit"] = base
    r = _analyze(http, target_url, request)
    if r.status_code >= 500:
        return None, Result("error", f"expected 200 with a saved result, the target failed with {_got(r)}", "system")
    body = _body(r)
    if r.status_code != 200 or not isinstance(body, dict):
        return None, Result("fail", f"expected 200 with a saved result, got {_got(r)}")
    problem = _schema_problem(body)
    if problem:
        return None, Result("fail", f"expected a schema-valid result, got one that breaks the schema: {problem}")
    if body["status"] != "SUCCESS":
        return None, Result("fail", f"expected status SUCCESS, got {body['status']}")
    return body, None


def _saved_runs(http: httpx.Client, target_url: str, commit: str, count: int) -> tuple[list[dict], Result | None]:
    # analyses a fixture commit count times, stopping at the first run that isn't a schema-valid SUCCESS result
    runs = []
    for _ in range(count):
        posted, failed = _saved_run(http, target_url, commit)
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
        return Result("fail", f"expected 200 for GET {path}, got {_got(r)}")
    served = _body(r)
    if served != posted:
        differ = _differing(posted, served) if isinstance(served, dict) else ["the whole body"]
        return Result("fail", f"expected GET {path} to return the POST body, it differs in {', '.join(differ)}")
    return None


def t14(http: httpx.Client, target_url: str) -> Result:
    # analyses c1-impl-only, then reads the run back
    runs, failed = _saved_runs(http, target_url, COMMITS["c1-impl-only"], 1)
    if failed:
        return failed
    return _served_back(http, target_url, runs[0]) or Result("pass", "GET /analysis/{id} returned the POST body")


def t16(http: httpx.Client, target_url: str) -> Result:
    # analyses c2-add-mod-del twice, expects two ids that each read back unchanged
    runs, failed = _saved_runs(http, target_url, COMMITS["c2-add-mod-del"], 2)
    if failed:
        return failed
    if runs[0]["analysis_id"] == runs[1]["analysis_id"]:
        return Result("fail", f"expected two different ids, got {runs[0]['analysis_id']} twice")
    for posted in runs:
        failed = _served_back(http, target_url, posted)
        if failed:
            return failed
    return Result("pass", "two runs got two ids, both read back unchanged")


def _significant(run: dict) -> dict:
    # keeps what T-17 compares: the significant fields, and the findings without their ids
    kept = {k: run.get(k) for k in SIGNIFICANT}
    kept["issues"] = [{k: v for k, v in f.items() if k != "finding_id"} for f in run["issues"]]
    return kept


def t17(http: httpx.Client, target_url: str) -> Result:
    # analyses c4-categories five times, expects schema-valid runs that agree on the significant fields and findings
    runs, failed = _saved_runs(http, target_url, COMMITS["c4-categories"], 5)
    if failed:
        return failed
    kept = [_significant(run) for run in runs]
    differ = sorted({field for run in kept[1:] for field in _differing(kept[0], run)})
    if differ:
        return Result("fail", f"expected five runs to agree on {', '.join(SIGNIFICANT)} and issues, they differ in {', '.join(differ)}")
    return Result("pass", f"five runs agree on {', '.join(SIGNIFICANT)} and issues")


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
    return {(s.get("path"), s.get("reason")) for s in skipped}


def _show(items: set) -> str:
    # words a set for a message, sorted, as {a, b}
    return "{" + ", ".join(sorted(str(i) if isinstance(i, ChangeKey) else " ".join(map(str, i)) for i in items)) + "}"


def _change_problems(case: dict, got: dict) -> list[str]:
    # compares a result with a change case the way Team 16's t01 to t07 do
    problems = []
    if case.get("root"):
        if got["base_commit"] is not None:
            problems.append(f"expected base_commit null for a root commit, got {got['base_commit']}")
        if len(got["changes"]) != len(case["root_paths"]) or any(c["change_type"] != "ADDED" for c in got["changes"]):
            problems.append(f"expected all {len(case['root_paths'])} files of the root commit as ADDED, got {len(got['changes'])} changes")
        return problems
    if "base_commit" in case and got["base_commit"] != case["base_commit"]:
        kind = "the base sent" if case.get("explicit_base") else "the first parent"
        problems.append(f"expected base_commit {case['base_commit']} ({case['base_tag']}, {kind}), got {got['base_commit']}")
    expected = {ChangeKey.of(c) for c in case["changes"]}
    received = {ChangeKey.of(c) for c in got["changes"]}
    if received != expected:
        problems.append(f"expected changes {_show(expected)}, got {_show(received)}")
    if "skipped" in case:
        want, have = _skips(case["skipped"]), _skips(got["skipped"])
        if have != want:
            problems.append(f"expected skipped {_show(want)}, got {_show(have)}")
    return problems


def change_test(case: dict) -> Callable[[httpx.Client, str], Result]:
    # builds one change test from its entry in the data file, sending the base only when the entry says so

    def check(http: httpx.Client, target_url: str) -> Result:
        # analyses the case's commit and names every way the answer differs from the expected one
        got, failed = _saved_run(http, target_url, case["commit"], case["base_commit"] if case.get("explicit_base") else None)
        if failed:
            return failed
        problems = _change_problems(case, got)
        if problems:
            return Result("fail", f"{case['title']}: " + "; ".join(problems))
        if case.get("root"):
            return Result("pass", f"{case['title']}: base_commit null and all {len(case['root_paths'])} files ADDED")
        also = f" and skipped {_show(_skips(case['skipped']))}" if "skipped" in case else ""
        return Result("pass", f"{case['title']}: got the expected changes {_show({ChangeKey.of(c) for c in case['changes']})}{also}")

    return check


class SharedTest(NamedTuple):
    # defines one shared test: its id, its judge, the components and criteria it exercises, and why it waits when it has no judge
    test_id: str
    check: Callable[[httpx.Client, str], Result] | None
    components: list[str]
    criteria: list[str]
    skip: str | None = None


# words Team 16's reasons for T-18 to T-20, which wait for the detector
PHASE_4 = "Documentation detection is the Phase 4 milestone (Phase 2, Section 6.2)."


# lists the shared tests in the order they run, with Team 16's tags, the change tests' from the data file
TESTS: list[SharedTest] = [
    *(SharedTest(c["test_id"], change_test(c), c["components"], c["criteria"]) for c in CHANGE_CASES),
    SharedTest("T-08", t08, ["C1"], ["AC-07"]),
    SharedTest("T-09", t09, ["C1"], ["AC-07"]),
    SharedTest("T-10", t10, ["C1"], ["AC-07"]),
    SharedTest("T-11", t11, ["C1"], ["AC-07"]),
    SharedTest("T-12", t12, ["C1", "C2"], ["AC-08"]),
    SharedTest("T-13", t13, ["C1", "C2"], ["AC-08"]),
    SharedTest("T-14", t14, ["C1", "C6"], ["AC-06"]),
    SharedTest("T-15", t15, ["C1", "C6"], ["AC-06", "AC-08"]),
    SharedTest("T-16", t16, ["C1", "C2", "C3", "C5", "C6"], ["AC-06"]),
    SharedTest("T-17", t17, ["C1", "C2", "C3", "C5"], ["AC-10"]),
    SharedTest("T-18", None, ["C4"], ["AC-02"], f"Missing mapped documentation finding: {PHASE_4}"),
    SharedTest("T-19", None, ["C4"], ["AC-02"], f"Unchanged mapped documentation finding: {PHASE_4}"),
    SharedTest("T-20", None, ["C4"], ["AC-03"], f"Code and documentation updated together: {PHASE_4}"),
    SharedTest(
        "T-21", None, ["C4", "C5"], ["AC-04"], "New findings start PENDING_REVIEW: Requires findings from the Phase 4 detector."
    ),
    SharedTest(
        "T-22", None, ["C7"], ["AC-05"],
        "Authorized and unauthorized review decisions: Review workflow is the Phase 5 milestone (Phase 2, Section 6.3).",
    ),
    SharedTest(
        "T-23", None, ["C2"], ["AC-09"],
        "Read-only analysis, no repository code execution: Requires source comparison and code inspection; scheduled for Phase 5.",
    ),
]


def _found(test: SharedTest, result: Result) -> dict:
    # words one result for the suite report, source only on an error
    found = {"test_id": test.test_id, "outcome": result.outcome, "message": result.message}
    if result.source is not None:
        found["source"] = result.source
    return found


def _run_one(http: httpx.Client, target_url: str, test: SharedTest) -> dict:
    # runs one test, a planned one is skipped, a call with no answer is an error from communication
    if test.check is None:
        return _found(test, Result("skip", test.skip or ""))
    try:
        result = test.check(http, target_url)
    except httpx.TransportError as exc:
        result = Result("error", f"the target gave no answer: {exc}", "communication")
    return _found(test, result)


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
    return {"covered": len(found), "total": len(listed), "basis": f"{what} exercised by at least one executed test: {names}"}


def tag_coverage(results: list[dict]) -> dict:
    # counts component and system coverage from the tags of every test that ran, a skipped test covers nothing
    ran = {r["test_id"] for r in results if r["outcome"] != "skip"}
    executed = [t for t in TESTS if t.test_id in ran]
    return {
        "component": _counted(
            COMPONENTS, {c for t in executed for c in t.components}, "Components C1-C7 listed in the pod specification"
        ),
        "system": _counted(
            CRITERIA, {c for t in executed for c in t.criteria}, "Acceptance criteria AC-01 to AC-10 in the pod specification"
        ),
    }


class Aborted(Exception):
    # carries the report of a suite cut short by its limit or a tester failure, and why

    def __init__(self, message: str, report: dict) -> None:
        super().__init__(message)
        self.message, self.report = message, report


def _report(session_id: str, target_url: str, results: list[dict], code: dict) -> dict:
    # builds the suite report in its field order
    return {
        "session_id": session_id,
        "target_url": target_url,
        "results": results,
        "coverage": {"code": code, **tag_coverage(results)},
    }


def _warm(http: httpx.Client, target_url: str) -> None:
    # wakes a sleeping target once before the tests, its answer is not judged
    try:
        http.get(f"{target_url}/health")
    except httpx.TransportError:
        pass


def run(session_id: str, target_url: str) -> dict:
    # runs every shared test once in a worker, raises Aborted past the suite limit or on a tester failure
    results: list[dict] = []
    code: dict = {}
    failure: list[Exception] = []
    lock, ended, stopped = threading.Lock(), threading.Event(), threading.Event()

    def work() -> None:
        # keeps each result as soon as it's known, and nothing once the suite was stopped
        try:
            with client() as http:
                _warm(http, target_url)
                for test in TESTS:
                    found = _run_one(http, target_url, test)
                    with lock:
                        if stopped.is_set():
                            return
                        results.append(found)
                code.update(code_coverage(http, target_url, session_id))
        except Exception as exc:
            failure.append(exc)
        finally:
            ended.set()

    threading.Thread(target=work, daemon=True).start()
    in_time = ended.wait(SUITE_TIMEOUT)
    with lock:
        stopped.set()
        done = list(results)
    if in_time and not failure:
        return _report(session_id, target_url, done, code)
    why = f"the tester failed: {failure[0]!r}" if failure else f"the suite passed its {SUITE_TIMEOUT:g} s limit"
    # marks the test in flight an error from the tester and every untried one skip
    for i, test in enumerate(TESTS[len(done):]):
        in_flight = i == 0 and test.check is not None
        done.append(_found(test, Result("error", f"not judged, {why}", "tester") if in_flight else Result("skip", test.skip or f"not run, {why}")))
    raise Aborted(f"the suite was aborted, {why}; GET /test/report has the results so far", _report(
        session_id, target_url, done, _uncounted(f"not read, {why}")
    ))
