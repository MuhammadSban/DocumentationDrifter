# covers cross-team tester ticket 02: T-08 to T-17, against the in-process /system and a stub that breaks one rule at a time

import httpx
import pytest
from tester_stub import CHANGE, analysis, assert_outcome, healthy, posted_json, results, rewrite, run, setup, suite_on_stub

# lists the tests ticket 02 adds, in the order they run
ORDER = [f"T-{n:02d}" for n in range(8, 18)]

# names each error test's expected answer, the stub's breakages are built from it
ERRORS = {
    "T-08": (400, "INVALID_REQUEST"),
    "T-09": (400, "INVALID_REQUEST"),
    "T-10": (400, "INVALID_REQUEST"),
    "T-11": (400, "INVALID_REQUEST"),
    "T-12": (404, "REPOSITORY_NOT_FOUND"),
    "T-13": (404, "COMMIT_NOT_FOUND"),
}


# --- against our system ----------------------------------------------


def test_t08_to_t17_run_in_order_and_pass_on_our_system(tester):
    sid = setup(tester).json()["session_id"]
    body = run(tester, sid).json()
    ids = [r["test_id"] for r in body["results"]]
    assert [i for i in ids if i in ORDER] == ORDER
    for test_id in ORDER:
        assert_outcome(results(body)[test_id], "pass")


# --- against a correct stub ------------------------------------------


def test_a_correct_stub_passes_every_test(stub, api):
    routes, _ = stub
    healthy(routes)
    found = suite_on_stub(api)
    for test_id in ORDER:
        assert_outcome(found[test_id], "pass")


def test_the_saved_result_tests_analyse_the_fixture_commit_by_full_sha(stub, api):
    from Tester import suite

    routes, calls = stub
    healthy(routes)
    suite_on_stub(api)
    fixture = {"repository": suite.FIXTURE_REPO, "commit_id": suite.FIXTURE_COMMIT}
    analyses = [c for c in calls if c.url.path.endswith("/analyze") and posted_json(c) == fixture]
    assert len(analyses) == 1 + 1 + 2 + 5  # counts T-01, T-14, T-16 and T-17
    assert len(suite.FIXTURE_COMMIT) == 40


# --- error tests, T-08 to T-13 ---------------------------------------


@pytest.mark.parametrize("test_id", list(ERRORS))
def test_an_error_test_passes_on_status_and_code_whatever_the_wording(stub, api, test_id):
    routes, _ = stub
    healthy(routes)
    status, code = ERRORS[test_id]
    routes[("POST", "/analyze")] = httpx.Response(status, json={"code": code, "message": "anything at all"})
    assert_outcome(suite_on_stub(api)[test_id], "pass")


@pytest.mark.parametrize("test_id", list(ERRORS))
@pytest.mark.parametrize(
    "answer",
    [
        lambda status, code: httpx.Response(status, json={"code": code, "message": ""}),
        lambda status, code: httpx.Response(status, json={"code": code}),
        lambda status, code: httpx.Response(status, json={"code": "SOMETHING_ELSE", "message": "x"}),
        lambda status, code: httpx.Response(status + 1, json={"code": code, "message": "x"}),
        lambda status, code: httpx.Response(200, json=analysis({"repository": "a/b", "commit_id": "c"})),
        lambda status, code: httpx.Response(status, text="not json"),
        lambda status, code: httpx.Response(500, json={"code": "TIMEOUT", "message": "slow"}),
    ],
    ids=["empty-message", "no-message", "wrong-code", "wrong-status", "success", "not-json", "listed-500"],
)
def test_an_error_test_fails_on_a_wrong_answer(stub, api, test_id, answer):
    routes, _ = stub
    healthy(routes)
    routes[("POST", "/analyze")] = answer(*ERRORS[test_id])
    result = suite_on_stub(api)[test_id]
    assert_outcome(result, "fail")
    assert str(ERRORS[test_id][0]) in result["message"]


@pytest.mark.parametrize("test_id", list(ERRORS))
@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(502, text="bad gateway"),
        httpx.Response(503, json={"code": "TIMEOUT", "message": "slow"}),
        httpx.Response(500, json={"code": "LLM_UNAVAILABLE", "message": "ours, not the pod's"}),
    ],
    ids=["502", "listed-code-on-503", "unlisted-code-on-500"],
)
def test_an_unlisted_5xx_is_an_error_from_the_system(stub, api, test_id, answer):
    routes, _ = stub
    healthy(routes)
    routes[("POST", "/analyze")] = answer
    assert_outcome(suite_on_stub(api)[test_id], "error", "system")


def test_no_answer_is_an_error_from_communication(stub, api):
    routes, _ = stub
    healthy(routes)

    def hang(request):
        raise httpx.ReadTimeout("slow", request=request)

    routes[("POST", "/analyze")] = hang
    found = suite_on_stub(api)
    for test_id in ORDER:
        if test_id != "T-15":
            assert_outcome(found[test_id], "error", "communication")


# --- saved results, T-14 and T-16 ------------------------------------


def test_t14_and_t16_fail_when_the_saved_run_differs_from_the_post(stub, api):
    routes, _ = stub
    healthy(routes)
    rewrite(routes, ("GET", "/analysis/*"), lambda body, n: {**body, "changes": []})
    found = suite_on_stub(api)
    for test_id in ("T-14", "T-16"):
        assert_outcome(found[test_id], "fail")
        assert "changes" in found[test_id]["message"]


def test_t14_and_t16_fail_when_the_saved_run_is_missing(stub, api):
    routes, _ = stub
    healthy(routes)
    routes[("GET", "/analysis/*")] = httpx.Response(404, json={"code": "ANALYSIS_NOT_FOUND", "message": "gone"})
    found = suite_on_stub(api)
    assert_outcome(found["T-14"], "fail")
    assert_outcome(found["T-16"], "fail")


def test_the_saved_result_tests_fail_when_the_analysis_fails(stub, api):
    routes, _ = stub
    healthy(routes)
    routes[("POST", "/analyze")] = httpx.Response(404, json={"code": "COMMIT_NOT_FOUND", "message": "no"})
    found = suite_on_stub(api)
    for test_id in ("T-14", "T-16", "T-17"):
        assert_outcome(found[test_id], "fail")
        assert "200" in found[test_id]["message"]


def test_t16_fails_when_two_runs_share_an_id(stub, api):
    from Tester import suite

    routes, _ = stub
    saved = healthy(routes)
    fixed = analysis({"repository": suite.FIXTURE_REPO, "commit_id": suite.FIXTURE_COMMIT})
    saved[fixed["analysis_id"]] = fixed
    routes[("POST", "/analyze")] = httpx.Response(200, json=fixed)
    found = suite_on_stub(api)
    assert_outcome(found["T-14"], "pass")
    assert_outcome(found["T-16"], "fail")


# --- repeatability, T-17 ---------------------------------------------


@pytest.mark.parametrize(
    "field, make",
    [
        ("tool_version", lambda n: f"stub-{n}"),
        ("changes", lambda n: [] if n % 2 else [CHANGE]),
        ("head_commit", lambda n: str(n) * 40),
    ],
)
def test_t17_fails_when_a_field_other_than_id_and_time_differs(stub, api, field, make):
    routes, _ = stub
    healthy(routes)
    rewrite(routes, ("POST", "/analyze"), lambda body, n: {**body, field: make(n)})
    result = suite_on_stub(api)["T-17"]
    assert_outcome(result, "fail")
    assert field in result["message"]


def test_t17_ignores_analysis_id_and_created_at(stub, api):
    routes, _ = stub
    healthy(routes)
    rewrite(routes, ("POST", "/analyze"), lambda body, n: {**body, "created_at": f"2026-10-18T00:00:0{n}.000Z"})
    assert_outcome(suite_on_stub(api)["T-17"], "pass")


@pytest.mark.parametrize(
    "broken",
    [
        lambda body: {k: v for k, v in body.items() if k != "skipped"},
        lambda body: {**body, "changes": "none"},
        lambda body: {**body, "status": "MAYBE"},
        lambda body: {**body, "analysis_id": 7},
        lambda body: {**body, "changes": [{"path": "a"}]},
        lambda body: {**body, "changes": [{**CHANGE, "change_type": "MOVED"}]},
        lambda body: {**body, "changes": [{**CHANGE, "category": "STUFF"}]},
        lambda body: {**body, "issues": [1]},
        lambda body: {**body, "skipped": ["x"]},
        lambda body: {**body, "error": {"oops": 1}},
    ],
    ids=[
        "missing-field", "changes-not-a-list", "bad-status", "id-not-a-string", "change-missing-fields",
        "bad-change-type", "bad-category", "issue-not-a-finding", "skip-not-an-object", "error-not-an-error-body",
    ],
)
def test_t17_fails_a_result_that_breaks_the_schema(stub, api, broken):
    routes, _ = stub
    healthy(routes)
    rewrite(routes, ("POST", "/analyze"), lambda body, n: broken(body))
    result = suite_on_stub(api)["T-17"]
    assert_outcome(result, "fail")
    assert "schema" in result["message"]
