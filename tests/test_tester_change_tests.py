# covers cross-team tester ticket 03: T-01 to T-07 as Team 16's tester runs them, judged from one data file

import subprocess

import httpx
import pytest
from tester_stub import assert_outcome, case_for, healthy, posted_json, results, rewrite, run, setup, suite_on_stub

# lists the change tests, in the order they run
ORDER = [f"T-{n:02d}" for n in range(1, 8)]
# lists the change tests that compare changes[] as a set, T-07 checks only the base, the count and ADDED
SET_COMPARED = ORDER[:-1]


def on_case(test_id: str, transform):
    # rewrites the stub's answer only for the head and base test_id analyses, T-03 and T-06 share a head
    case = case_for(test_id)

    def maybe(body, n):
        # rewrites one case's body, every other body unchanged
        mine = body["head_commit"] == case["commit"] and body["base_commit"] == case.get("base_commit")
        return transform(body) if mine else body

    return maybe


# --- the data file ---------------------------------------------------


def test_the_data_file_names_every_change_test_with_its_tag_and_full_sha():
    from Tester import suite

    cases = {c["test_id"]: c for c in suite.CHANGE_CASES}
    assert list(cases) == ORDER
    for case in cases.values():
        assert case["commit"] == suite.COMMITS[case["tag"]] and len(case["commit"]) == 40
    assert cases["T-06"]["explicit_base"] and cases["T-06"]["base_commit"] == suite.COMMITS["c0-initial"]
    assert cases["T-07"]["root"] and cases["T-07"]["base_commit"] is None


def test_the_data_file_matches_the_local_fixture_repo(pod_fixtures):
    from Tester import suite

    def sha(rev: str) -> str:
        # resolves a revision in the local fixture repo
        return subprocess.run(["git", "rev-parse", rev], cwd=pod_fixtures, capture_output=True, text=True, check=True).stdout.strip()

    for tag, commit in suite.COMMITS.items():
        assert sha(f"{tag}^{{commit}}") == commit, tag
    assert sha(f"{suite.COMMITS['c1-impl-only']}^") == case_for("T-01")["base_commit"]


# --- against our system ----------------------------------------------


def test_our_system_passes_every_change_test(tester):
    sid = setup(tester).json()["session_id"]
    found = results(run(tester, sid).json())
    assert [t for t in found if t in ORDER] == ORDER
    for test_id in ORDER:
        assert_outcome(found[test_id], "pass")


# --- against a stub --------------------------------------------------


def test_a_stub_giving_the_expected_answers_passes_every_change_test(stub, api):
    routes, _ = stub
    healthy(routes)
    found = suite_on_stub(api)
    for test_id in ORDER:
        assert_outcome(found[test_id], "pass")


def test_the_change_tests_send_each_commit_by_full_sha_with_a_base_only_for_t06(stub, api):
    from Tester import suite

    routes, calls = stub
    healthy(routes)
    suite_on_stub(api)
    sent = [posted_json(c) for c in calls if c.url.path.endswith("/analyze")]
    for case in suite.CHANGE_CASES:
        request = {"repository": suite.FIXTURE_REPO, "commit_id": case["commit"]}
        if case.get("explicit_base"):
            request["base_commit"] = case["base_commit"]
        assert request in sent, case["test_id"]


@pytest.mark.parametrize("test_id", SET_COMPARED)
def test_swapping_one_category_fails_exactly_that_test(stub, api, test_id):
    routes, _ = stub
    healthy(routes)

    def swap(body):
        first, *rest = body["changes"]
        other = "OTHER" if first["category"] != "OTHER" else "IMPLEMENTATION"
        return {**body, "changes": [{**first, "category": other}, *rest]}

    rewrite(routes, ("POST", "/analyze"), on_case(test_id, swap))
    found = suite_on_stub(api)
    assert_outcome(found[test_id], "fail")
    message = found[test_id]["message"]
    assert "expected" in message and "got" in message and case_for(test_id)["changes"][0]["path"] in message
    for other in ORDER:
        if other != test_id:
            assert_outcome(found[other], "pass")


def test_t07_ignores_the_categories_as_team_16s_does(stub, api):
    routes, _ = stub
    healthy(routes)
    rewrite(routes, ("POST", "/analyze"), on_case("T-07", lambda b: {**b, "changes": [{**c, "category": "DESIGN"} for c in b["changes"]]}))
    assert_outcome(suite_on_stub(api)["T-07"], "pass")


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
    rewrite(routes, ("POST", "/analyze"), on_case("T-02", transform))
    assert_outcome(suite_on_stub(api)["T-02"], "fail")


def test_t03_fails_without_the_old_path(stub, api):
    routes, _ = stub
    healthy(routes)
    rewrite(routes, ("POST", "/analyze"), on_case("T-03", lambda b: {**b, "changes": [{**b["changes"][0], "old_path": None}]}))
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
    rewrite(routes, ("POST", "/analyze"), on_case("T-05", transform))
    result = suite_on_stub(api)["T-05"]
    assert_outcome(result, "fail")
    assert "skipped" in result["message"]


@pytest.mark.parametrize("test_id, label", [("T-01", "first parent"), ("T-06", "base sent")])
def test_t01_and_t06_check_the_base_the_system_used(stub, api, test_id, label):
    routes, _ = stub
    healthy(routes)
    rewrite(routes, ("POST", "/analyze"), on_case(test_id, lambda b: {**b, "base_commit": "a" * 40}))
    result = suite_on_stub(api)[test_id]
    assert_outcome(result, "fail")
    assert "base_commit" in result["message"] and label in result["message"]


@pytest.mark.parametrize(
    "transform, words",
    [
        (lambda b: {**b, "base_commit": "a" * 40}, "base_commit null"),
        (lambda b: {**b, "changes": b["changes"][1:]}, "all 11 files"),
        (lambda b: {**b, "changes": [{**b["changes"][0], "change_type": "MODIFIED"}, *b["changes"][1:]]}, "all 11 files"),
    ],
    ids=["base-not-null", "ten-files", "one-not-added"],
)
def test_t07_needs_a_null_base_and_all_11_files_added(stub, api, transform, words):
    routes, _ = stub
    healthy(routes)
    rewrite(routes, ("POST", "/analyze"), on_case("T-07", transform))
    result = suite_on_stub(api)["T-07"]
    assert_outcome(result, "fail")
    assert words in result["message"]


def test_a_change_test_needs_status_success(stub, api):
    routes, _ = stub
    healthy(routes)
    rewrite(routes, ("POST", "/analyze"), on_case("T-01", lambda b: {**b, "status": "ERROR"}))
    result = suite_on_stub(api)["T-01"]
    assert_outcome(result, "fail")
    assert "SUCCESS" in result["message"]


def test_a_failed_analysis_is_an_error_from_the_system(stub, api):
    routes, _ = stub
    healthy(routes)
    routes[("POST", "/analyze")] = httpx.Response(502, text="bad gateway")
    found = suite_on_stub(api)
    for test_id in ORDER:
        assert_outcome(found[test_id], "error", "system")
