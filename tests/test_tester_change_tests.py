# covers cross-team tester ticket 03: T-01 to T-07, change detection on the pod fixture repo, judged from one data file

import subprocess

import httpx
import pytest
from tester_stub import assert_outcome, case_for, healthy, posted_json, results, rewrite, run, setup, suite_on_stub

# lists the tests ticket 03 adds, in the order they run
ORDER = [f"T-{n:02d}" for n in range(1, 8)]
RAN = [t for t in ORDER if t != "T-06"]


def on_commit(test_id: str, transform):
    # rewrites the stub's answer only for the commit test_id analyses
    commit = case_for(test_id)["commit"]

    def maybe(body, n):
        # rewrites one commit's body, every other body unchanged
        return transform(body) if body["head_commit"] == commit else body

    return maybe


# --- the data file ---------------------------------------------------


def test_the_data_file_names_every_change_test_with_its_tag_and_full_sha():
    from Tester import suite

    cases = {c["test_id"]: c for c in suite.CHANGE_CASES}
    assert list(cases) == ORDER
    for test_id in RAN:
        assert len(cases[test_id]["commit"]) == 40 and cases[test_id]["tag"]
    assert cases["T-06"]["skip"]
    assert suite.FIXTURE_COMMIT == cases["T-01"]["commit"]


def test_the_data_file_matches_the_local_fixture_repo(pod_fixtures):
    from Tester import suite

    for case in suite.CHANGE_CASES:
        if "tag" not in case:
            continue
        sha = subprocess.run(
            ["git", "rev-parse", f"{case['tag']}^{{commit}}"], cwd=pod_fixtures, capture_output=True, text=True, check=True
        ).stdout.strip()
        assert sha == case["commit"], case["test_id"]


# --- against our system ----------------------------------------------


def test_t01_to_t03_pass_on_our_system(tester):
    # leaves T-04, T-05 and T-07 to tickets 06 and 07, our rules lack DESIGN and the other design-side categories
    sid = setup(tester).json()["session_id"]
    found = results(run(tester, sid).json())
    ids = [t for t in found if t in ORDER]
    assert ids == ORDER
    for test_id in ("T-01", "T-02", "T-03"):
        assert_outcome(found[test_id], "pass")


# --- against a stub --------------------------------------------------


def test_a_stub_giving_the_expected_answers_passes_every_change_test(stub, api):
    routes, _ = stub
    healthy(routes)
    found = suite_on_stub(api)
    for test_id in RAN:
        assert_outcome(found[test_id], "pass")
    assert_outcome(found["T-06"], "skip")


def test_the_change_tests_analyse_each_commit_by_full_sha_without_a_base(stub, api):
    from Tester import suite

    routes, calls = stub
    healthy(routes)
    suite_on_stub(api)
    sent = [posted_json(c) for c in calls if c.url.path.endswith("/analyze")]
    for case in suite.CHANGE_CASES:
        if "commit" in case:
            assert {"repository": suite.FIXTURE_REPO, "commit_id": case["commit"]} in sent


@pytest.mark.parametrize("test_id", RAN)
def test_swapping_one_category_fails_exactly_that_test(stub, api, test_id):
    routes, _ = stub
    healthy(routes)

    def swap(body):
        first, *rest = body["changes"]
        other = "OTHER" if first["category"] != "OTHER" else "IMPLEMENTATION"
        return {**body, "changes": [{**first, "category": other}, *rest]}

    rewrite(routes, ("POST", "/analyze"), on_commit(test_id, swap))
    found = suite_on_stub(api)
    assert_outcome(found[test_id], "fail")
    message = found[test_id]["message"]
    assert "expected" in message and "got" in message and case_for(test_id)["changes"][0]["path"] in message
    for other in RAN:
        if other != test_id:
            assert_outcome(found[other], "pass")


@pytest.mark.parametrize(
    "transform",
    [
        lambda body: {**body, "changes": body["changes"][1:]},
        lambda body: {**body, "changes": [*body["changes"], {**body["changes"][0], "path": "extra.py"}]},
        lambda body: {**body, "changes": [{**c, "change_type": "ADDED"} for c in body["changes"]]},
    ],
    ids=["one-missing", "one-extra", "wrong-change-type"],
)
def test_t02_fails_on_a_missing_extra_or_mistyped_change(stub, api, transform):
    routes, _ = stub
    healthy(routes)
    rewrite(routes, ("POST", "/analyze"), on_commit("T-02", transform))
    assert_outcome(suite_on_stub(api)["T-02"], "fail")


def test_t03_fails_without_the_old_path(stub, api):
    routes, _ = stub
    healthy(routes)
    rewrite(routes, ("POST", "/analyze"), on_commit("T-03", lambda b: {**b, "changes": [{**b["changes"][0], "old_path": None}]}))
    assert_outcome(suite_on_stub(api)["T-03"], "fail")


@pytest.mark.parametrize(
    "transform",
    [
        lambda body: {**body, "skipped": []},
        lambda body: {**body, "skipped": body["skipped"][:1]},
        lambda body: {**body, "skipped": [{**s, "reason": "BINARY_FILE"} for s in body["skipped"]]},
    ],
    ids=["none-skipped", "one-skipped", "other-reason"],
)
def test_t05_checks_the_skipped_paths_and_their_reason(stub, api, transform):
    routes, _ = stub
    healthy(routes)
    rewrite(routes, ("POST", "/analyze"), on_commit("T-05", transform))
    result = suite_on_stub(api)["T-05"]
    assert_outcome(result, "fail")
    assert "skipped" in result["message"]


def test_t07_needs_a_null_base_commit(stub, api):
    routes, _ = stub
    healthy(routes)
    rewrite(routes, ("POST", "/analyze"), on_commit("T-07", lambda b: {**b, "base_commit": "a" * 40}))
    result = suite_on_stub(api)["T-07"]
    assert_outcome(result, "fail")
    assert "base_commit" in result["message"]


def test_a_failed_analysis_fails_or_errors_the_change_test(stub, api):
    routes, _ = stub
    healthy(routes)
    routes[("POST", "/analyze")] = httpx.Response(502, text="bad gateway")
    found = suite_on_stub(api)
    for test_id in RAN:
        assert_outcome(found[test_id], "error", "system")
    assert_outcome(found["T-06"], "skip")
