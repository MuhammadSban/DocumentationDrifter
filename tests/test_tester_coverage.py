# covers cross-team tester ticket 04: component and system coverage counted from each shared test's tags

import pytest
from tester_stub import healthy, results, run, setup, suite_on_stub

COMPONENTS = [f"C{n}" for n in range(1, 8)]
CRITERIA = [f"AC-{n:02d}" for n in range(1, 11)]


def outcomes(skip: set[str] = frozenset()) -> list[dict]:
    # makes one result per shared test, skip for the ids given and pass for the rest
    from Tester import suite

    return [
        {"test_id": t.test_id, "outcome": "skip" if t.test_id in skip else "pass", "message": "m"}
        for t in suite.TESTS
    ]


# --- the tags --------------------------------------------------------


def test_every_shared_test_carries_component_and_criteria_tags():
    from Tester import suite

    for t in suite.TESTS:
        assert t.components and set(t.components) <= set(COMPONENTS), t.test_id
        assert t.criteria and set(t.criteria) <= set(CRITERIA), t.test_id


def test_the_change_tests_take_their_tags_from_the_data_file():
    from Tester import suite

    tags = {t.test_id: (t.components, t.criteria) for t in suite.TESTS}
    for case in suite.CHANGE_CASES:
        assert tags[case["test_id"]] == (case["components"], case["criteria"])


# --- counting --------------------------------------------------------


def test_t01_to_t17_executed_gives_team_16s_numbers():
    from Tester import suite

    coverage = suite.tag_coverage(outcomes(skip={"T-06"}))
    assert coverage["component"]["covered"] == 5 and coverage["component"]["total"] == 7
    assert coverage["component"]["basis"].endswith(": C1, C2, C3, C5, C6")
    assert coverage["system"]["covered"] == 5 and coverage["system"]["total"] == 10
    assert coverage["system"]["basis"].endswith(": AC-01, AC-06, AC-07, AC-08, AC-10")


def test_the_basis_reads_word_for_word_as_team_16s():
    # copies both sentences from Team 16's live report against their own system, 2026-10-18
    from Tester import suite

    coverage = suite.tag_coverage(outcomes())
    assert coverage["component"]["basis"] == (
        "Components C1-C7 listed in the pod specification exercised by at least one executed test: C1, C2, C3, C5, C6"
    )
    assert coverage["system"]["basis"] == (
        "Acceptance criteria AC-01 to AC-10 in the pod specification exercised by at least one executed test: "
        "AC-01, AC-06, AC-07, AC-08, AC-10"
    )


def test_a_skipped_test_covers_nothing():
    from Tester import suite

    everything = {t.test_id for t in suite.TESTS}
    coverage = suite.tag_coverage(outcomes(skip=everything - {"T-15"}))
    assert coverage["component"]["covered"] == 2 and coverage["component"]["basis"].endswith(": C1, C6")
    assert coverage["system"]["covered"] == 2 and coverage["system"]["basis"].endswith(": AC-06, AC-08")


def test_all_skipped_covers_none_but_still_counts():
    from Tester import suite

    coverage = suite.tag_coverage(outcomes(skip={t.test_id for t in suite.TESTS}))
    for kind, total in (("component", 7), ("system", 10)):
        assert coverage[kind]["covered"] == 0 and coverage[kind]["total"] == total
        assert coverage[kind]["basis"].endswith(": none")


@pytest.mark.parametrize("outcome", ["fail", "error"])
def test_a_failed_or_errored_test_still_counts_as_executed(outcome):
    from Tester import suite

    found = [{**r, "outcome": outcome} if r["test_id"] == "T-15" else {**r, "outcome": "skip"} for r in outcomes()]
    assert suite.tag_coverage(found)["component"]["covered"] == 2


# --- in the suite report ---------------------------------------------


def test_the_suite_report_counts_both_kinds(stub, api):
    routes, _ = stub
    healthy(routes)
    sid = setup(api, "http://stub.test/system").json()["session_id"]
    coverage = run(api, sid).json()["coverage"]
    assert list(coverage) == ["code", "component", "system"]
    for kind, total in (("component", 7), ("system", 10)):
        assert coverage[kind]["total"] == total and 0 <= coverage[kind]["covered"] <= total
        assert coverage[kind]["basis"]
    assert coverage["component"]["covered"] == 5 and coverage["system"]["covered"] == 5


def test_our_system_gets_the_same_numbers(tester):
    sid = setup(tester).json()["session_id"]
    coverage = run(tester, sid).json()["coverage"]
    assert (coverage["component"]["covered"], coverage["system"]["covered"]) == (5, 5)
