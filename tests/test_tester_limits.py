# covers cross-team tester ticket 05: the call and suite limits, aborts, one run per session, and the planned skips

import threading

import httpx
import pytest
from tester_stub import STUB, assert_error, assert_outcome, healthy, results, run, setup, suite_on_stub

# copies T-18 to T-23 from Team 16's suite (ParthGupta06/doc-tracker, doctracker/tester/suite.py at 0db21ca)
PLANNED_SKIPS = {
    "T-18": "Missing mapped documentation finding: Documentation detection is the Phase 4 milestone (Phase 2, Section 6.2).",
    "T-19": "Unchanged mapped documentation finding: Documentation detection is the Phase 4 milestone (Phase 2, Section 6.2).",
    "T-20": "Code and documentation updated together: Documentation detection is the Phase 4 milestone (Phase 2, Section 6.2).",
    "T-21": "New findings start PENDING_REVIEW: Requires findings from the Phase 4 detector.",
    "T-22": "Authorized and unauthorized review decisions: Review workflow is the Phase 5 milestone (Phase 2, Section 6.3).",
    "T-23": "Read-only analysis, no repository code execution: Requires source comparison and code inspection; scheduled for Phase 5.",
}
PLANNED_TAGS = {
    "T-18": (["C4"], ["AC-02"]), "T-19": (["C4"], ["AC-02"]), "T-20": (["C4"], ["AC-03"]),
    "T-21": (["C4", "C5"], ["AC-04"]), "T-22": (["C7"], ["AC-05"]), "T-23": (["C2"], ["AC-09"]),
}


def report(api, sid):
    # reads a session's stored suite report
    return api.get("/tester/test/report", params={"session_id": sid})


@pytest.fixture
def hang(stub):
    # makes T-15's lookup hang until the test ends, the target's other routes healthy, returns the event set once it hangs
    from Tester import suite

    routes, _ = stub
    healthy(routes)
    lookup = routes[("GET", "/analysis/*")]
    entered, release = threading.Event(), threading.Event()

    def stuck(request):
        if not request.url.path.endswith(suite.UNKNOWN_ANALYSIS):
            return lookup(request)
        entered.set()
        release.wait(30)
        return httpx.Response(404, json={"code": "ANALYSIS_NOT_FOUND", "message": "late"})

    routes[("GET", "/analysis/*")] = stuck
    yield entered
    release.set()


# --- the limits ------------------------------------------------------


def test_both_limits_default_to_90_and_600_seconds():
    from Tester import suite

    assert suite.CALL_TIMEOUT == 90.0 and suite.SUITE_TIMEOUT == 600.0


def test_the_limits_come_from_the_environment(monkeypatch):
    import importlib

    from Tester import suite

    monkeypatch.setenv("TESTER_CALL_TIMEOUT", "5")
    monkeypatch.setenv("TESTER_SUITE_TIMEOUT", "50")
    try:
        importlib.reload(suite)
        assert suite.CALL_TIMEOUT == 5.0 and suite.SUITE_TIMEOUT == 50.0
    finally:
        monkeypatch.delenv("TESTER_CALL_TIMEOUT")
        monkeypatch.delenv("TESTER_SUITE_TIMEOUT")
        importlib.reload(suite)


def test_a_run_starts_with_one_health_warm_up(stub, api):
    routes, calls = stub
    healthy(routes)
    sid = setup(api, STUB).json()["session_id"]
    run(api, sid)
    assert str(calls[1].url) == STUB + "/health"
    assert sum(c.url.path.endswith("/health") for c in calls) == 1


def test_a_hung_test_ends_the_run_within_the_suite_limit(hang, api, monkeypatch):
    import time

    from Tester import suite

    monkeypatch.setattr(suite, "SUITE_TIMEOUT", 1.0)
    sid = setup(api, STUB).json()["session_id"]
    started = time.monotonic()
    r = run(api, sid)
    assert time.monotonic() - started < 5
    assert_error(r, 500, "tester")
    stored = report(api, sid)
    assert stored.status_code == 200
    found = results(stored.json())
    ids = list(found)
    assert ids == [t.test_id for t in suite.TESTS]
    assert all(found[i]["outcome"] != "skip" for i in ids[: ids.index("T-15")] if i not in PLANNED_SKIPS)
    assert_outcome(found["T-15"], "error", "tester")
    assert all(found[i]["outcome"] == "skip" and found[i]["message"] for i in ids[ids.index("T-15") + 1 :])
    assert stored.json()["coverage"]["code"]["covered"] is None


def test_a_hung_run_stores_the_same_report_on_a_second_read(hang, api, monkeypatch):
    from Tester import suite

    monkeypatch.setattr(suite, "SUITE_TIMEOUT", 1.0)
    sid = setup(api, STUB).json()["session_id"]
    run(api, sid)
    assert report(api, sid).content == report(api, sid).content


def test_one_call_timing_out_alone_is_still_a_communication_error(stub, api):
    routes, _ = stub
    healthy(routes)

    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    routes[("GET", "/analysis/*")] = slow
    sid = setup(api, STUB).json()["session_id"]
    r = run(api, sid)
    assert r.status_code == 200
    assert_outcome(results(r.json())["T-15"], "error", "communication")


def test_a_tester_failure_aborts_the_run_the_same_way(stub, api, monkeypatch):
    from Tester import suite

    routes, _ = stub
    healthy(routes)

    def broken(http, target_url):
        raise RuntimeError("tester bug")

    tests = [t._replace(check=broken) if t.test_id == "T-10" else t for t in suite.TESTS]
    monkeypatch.setattr(suite, "TESTS", tests)
    sid = setup(api, STUB).json()["session_id"]
    assert_error(run(api, sid), 500, "tester")
    found = results(report(api, sid).json())
    assert_outcome(found["T-10"], "error", "tester")
    assert found["T-09"]["outcome"] == "pass"
    assert all(found[i]["outcome"] == "skip" for i in list(found)[list(found).index("T-10") + 1 :])


# --- one run per session ---------------------------------------------


def test_a_repeated_run_is_409_and_leaves_the_report_unchanged(stub, api):
    routes, calls = stub
    healthy(routes)
    sid = setup(api, STUB).json()["session_id"]
    first = run(api, sid)
    seen = len(calls)
    assert_error(run(api, sid), 409, "tester")
    assert len(calls) == seen
    assert report(api, sid).content == first.content


def test_a_run_after_an_abort_is_409(hang, api, monkeypatch):
    from Tester import suite

    monkeypatch.setattr(suite, "SUITE_TIMEOUT", 1.0)
    sid = setup(api, STUB).json()["session_id"]
    run(api, sid)
    stored = report(api, sid).content
    assert_error(run(api, sid), 409, "tester")
    assert report(api, sid).content == stored


def test_a_concurrent_run_is_409_and_starts_no_second_suite(hang, api, monkeypatch):
    from Tester import suite

    monkeypatch.setattr(suite, "SUITE_TIMEOUT", 2.0)
    sid = setup(api, STUB).json()["session_id"]
    first: dict = {}
    worker = threading.Thread(target=lambda: first.update(r=run(api, sid)))
    worker.start()
    assert hang.wait(10)
    assert_error(report(api, sid), 409, "tester")
    second = run(api, sid)
    worker.join()
    assert_error(second, 409, "tester")
    assert first["r"].status_code == 500
    assert sum(r["test_id"] == "T-01" for r in report(api, sid).json()["results"]) == 1


# --- the planned skips -----------------------------------------------


def test_t18_to_t23_are_skipped_with_team_16s_reasons(stub, api):
    routes, _ = stub
    healthy(routes)
    found = suite_on_stub(api)
    for test_id, message in PLANNED_SKIPS.items():
        assert found[test_id] == {"test_id": test_id, "outcome": "skip", "message": message}


def test_t18_to_t23_carry_team_16s_tags_and_come_last():
    from Tester import suite

    ids = [t.test_id for t in suite.TESTS]
    assert ids == [f"T-{n:02d}" for n in range(1, 24)]
    tags = {t.test_id: (t.components, t.criteria) for t in suite.TESTS}
    for test_id, expected in PLANNED_TAGS.items():
        assert tags[test_id] == expected


def test_the_planned_skips_leave_the_coverage_counts_alone(stub, api):
    routes, _ = stub
    healthy(routes)
    sid = setup(api, STUB).json()["session_id"]
    coverage = run(api, sid).json()["coverage"]
    assert coverage["component"]["covered"] == 5 and coverage["system"]["covered"] == 5
