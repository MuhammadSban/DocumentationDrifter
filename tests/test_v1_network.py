# covers ticket 09: GitHub, anonymous not-found, schema and conformance, repo-visibility checks live in private_tests and public_tests

import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx
import pytest

import reference

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import testrepo  # noqa: E402

MISSING_REPO = "octocat/this-repo-cannot-exist-7f3a9c"
HELLO = {"repository": "octocat/Hello-World", "commit_id": "7fd1a60"}


@pytest.mark.network
def test_hello_world_through_github(api, github_env):
    r = api.post("/system/analyze", json=HELLO)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["head_commit"] == "7fd1a60b01f91b314f59955a4e4d4e80d8edf11d"
    assert body["base_commit"].startswith("553c2077")
    assert [(c["path"], c["change_type"]) for c in body["changes"]] == [("README", "MODIFIED")]
    assert api.get(f"/system/analysis/{body['analysis_id']}").content == r.content


@pytest.mark.network
def test_missing_repository_fails_fast_without_credentials(api, github_env, recorded_helper):
    start = time.monotonic()
    r = api.post("/system/analyze", json={"repository": MISSING_REPO, "commit_id": "a" * 40})
    assert time.monotonic() - start < 15
    assert r.status_code == 404
    assert r.json()["code"] == "REPOSITORY_NOT_FOUND"
    assert not recorded_helper.exists(), "a credential helper was asked for credentials"


# --- schema ----------------------------------------------------------


def our_openapi():
    # reads our published OpenAPI document from the in-process app
    from fastapi.testclient import TestClient

    from GitHub_Connector.api import app

    return TestClient(app).get("/system/openapi.json").json()


def test_our_schema_matches_the_captured_reference():
    if not reference.CAPTURED_OPENAPI.exists():
        pytest.skip("no captured reference document yet: run `python tests/reference.py capture`")
    theirs = json.loads(reference.CAPTURED_OPENAPI.read_text())
    assert reference.schema_differences(our_openapi(), theirs) == []


def test_schema_comparison_catches_a_real_difference():
    # guards the comparison itself: an extra field or enum value must show up
    ours = our_openapi()
    theirs = json.loads(json.dumps(ours))
    assert reference.schema_differences(ours, theirs) == []
    theirs["components"]["schemas"]["Change"]["properties"]["extra"] = {"type": "string"}
    theirs["components"]["schemas"]["ChangeType"]["enum"].append("EXTRA")
    found = reference.schema_differences(ours, theirs)
    assert any("Change.extra" in f for f in found)
    assert any("Change.change_type" in f for f in found)


def test_our_schema_has_the_reference_shapes():
    # pins the two details the live comparison found on 2026-10-17
    doc = our_openapi()
    schemas = doc["components"]["schemas"]
    assert schemas["ErrorBody"]["properties"]["code"] == {"type": "string", "title": "Code"}
    assert "documentation_file" in schemas["Finding"]["required"]


@pytest.mark.network
def test_our_schema_matches_the_live_reference(live_reference):
    theirs = httpx.get(f"{live_reference}/openapi.json", timeout=60).json()
    found = reference.schema_differences(our_openapi(), theirs)
    assert found == [], " | ".join(found)


# --- conformance -----------------------------------------------------


def theirs(method, path, body=None):
    # sends one request to the reference service
    r = httpx.request(method, reference.REFERENCE_URL + path, json=body, timeout=180)
    return r


def analyze(body):
    # spells a POST /analyze case
    return ("POST", "/analyze", body)


HELLO_FULL = "7fd1a60b01f91b314f59955a4e4d4e80d8edf11d"

# lists the conformance requests, real repos then every error case (ticket 12)
CASES = {
    "hello-world": analyze(HELLO),
    "hello-world-explicit-parent": analyze({**HELLO, "base_commit": "553c2077f0edc3d5dc5d17262f6aa498e69d6f8e"}),
    "hello-world-older-base": analyze({**HELLO, "base_commit": "7629413"}),
    "psf-requests": analyze({"repository": "psf/requests", "commit_id": "d568f47"}),
    "missing-commit-id": analyze({"repository": "octocat/Hello-World"}),
    "malformed-repository": analyze({"repository": "not-a-repo", "commit_id": HELLO_FULL}),
    "malformed-sha": analyze({"repository": "octocat/Hello-World", "commit_id": "xyz"}),
    "wrong-json-types": analyze({"repository": 7, "commit_id": HELLO_FULL}),
    "missing-repository": analyze({"repository": MISSING_REPO, "commit_id": "a" * 40}),
    "unknown-commit": analyze({"repository": "octocat/Hello-World", "commit_id": "1" * 40}),
    "unknown-base-commit": analyze({**HELLO, "base_commit": "2" * 40}),
    "unfetchable-short-sha": analyze({"repository": "octocat/Hello-World", "commit_id": "1234567"}),
    "unknown-analysis-id": ("GET", "/analysis/an-" + "0" * 32, None),
    "malformed-analysis-id": ("GET", "/analysis/not-an-id", None),
    "health": ("GET", "/health", None),
    # covers the course routes' error answers (ticket 14), each needs no session to exist
    "course-report-unknown-session": ("GET", "/test/report?session_id=drifter-conformance-never-set-up", None),
    "course-report-missing-session-id": ("GET", "/test/report", None),
    "course-report-empty-session-id": ("GET", "/test/report?session_id=", None),
    "course-setup-missing-session-id": ("POST", "/test/setup", {}),
    "course-setup-wrong-types": ("POST", "/test/setup", {"session_id": 7}),
    "course-setup-blank-session-id": ("POST", "/test/setup", {"session_id": ""}),
    "course-setup-long-session-id": ("POST", "/test/setup", {"session_id": "x" * 201}),
    "course-setup-wrong-setup-type": ("POST", "/test/setup", {"session_id": "x", "setup": "str"}),
    "course-setup-array-body": ("POST", "/test/setup", [1]),
    "course-setup-null-session-id": ("POST", "/test/setup", {"session_id": None}),
    "course-setup-null-setup": ("POST", "/test/setup", {"session_id": "x", "setup": None}),
    "course-setup-array-setup": ("POST", "/test/setup", {"session_id": "x", "setup": [1]}),
    "course-setup-no-body": ("POST", "/test/setup", None),
}


def label_cases():
    # adds every test-repo label when DRIFTER_LABEL_CONFORMANCE=1, on in the acceptance workflow
    if os.environ.get("DRIFTER_LABEL_CONFORMANCE") != "1":
        return {}
    return {f"label-{name}": ("POST", "/analyze", None) for name in testrepo.LABELS}


@pytest.mark.network
@pytest.mark.parametrize("case", sorted({**CASES, **label_cases()}))
def test_conformance(case, target, github_env, live_reference, request):
    if case.startswith("label-"):
        built = request.getfixturevalue("built")
        entry = built[2]["labels"][case[len("label-"):]]
        repo = os.environ.get("DRIFTER_TEST_REPO", testrepo.PUBLIC_REPO)
        method, path, body = "POST", "/analyze", {"repository": repo, **entry["request"]}
    else:
        method, path, body = CASES[case]
    ours = target.request(method, "/system" + path, json=body)
    their = theirs(method, path, body)
    assert ours.status_code == their.status_code, f"{case}: status ours {ours.status_code}, theirs {their.status_code}"
    found = reference.differences(*reference.comparable(reference.normalise(ours.json()), reference.normalise(their.json())))
    allowed = reference.KNOWN_CASE_DIFFERENCES.get(case, ("",))[0]
    found = [f for f in found if not (allowed and f.startswith(allowed + ":"))]
    assert found == [], f"{case}: " + " | ".join(found)
    if method == "POST" and ours.status_code == 200:
        # checks each service serves back its own POST bytes
        assert target.get(f"/system/analysis/{ours.json()['analysis_id']}").content == ours.content
        assert theirs("GET", f"/analysis/{their.json()['analysis_id']}").content == their.content


@pytest.mark.network
def test_course_session_conformance(target, github_env, live_reference):
    # opens the same fresh session on both services, then compares setup, repeat setup and report
    sid = f"drifter-conformance-{uuid.uuid4().hex}"
    for body in ({"session_id": sid, "setup": {"probe": True}}, {"session_id": sid}):
        ours = target.post("/system/test/setup", json=body)
        their = theirs("POST", "/test/setup", body)
        assert (ours.status_code, ours.json()) == (their.status_code, their.json()), f"setup: ours {ours.text}, theirs {their.text}"
    ours = target.get("/system/test/report", params={"session_id": sid})
    their = theirs("GET", f"/test/report?session_id={sid}")
    assert ours.status_code == their.status_code == 200
    # compares only the shape, the counts and basis describe two different codebases
    assert reference.key_shape(ours.json()) == reference.key_shape(their.json())


def test_differences_name_the_field_and_allow_only_known_ones():
    ours = {"config_version": "abc", "changes": [{"path": "d.md", "category": "DOCUMENTATION", "change_type": "ADDED"}]}
    same = {"config_version": "mapping-v1", "changes": [{"path": "d.md", "category": "OTHER", "change_type": "ADDED"}]}
    assert reference.differences(ours, same) == []
    other = {"config_version": "x", "changes": [{"path": "d.md", "category": "OTHER", "change_type": "MODIFIED"}]}
    assert reference.differences(ours, other) == ["body.changes[0].change_type: ours 'ADDED', theirs 'MODIFIED'"]
    swapped = {"config_version": "x", "changes": [{"path": "d.md", "category": "IMPLEMENTATION", "change_type": "ADDED"}]}
    assert reference.differences(ours, swapped) != []


def test_known_differences_by_choice_are_removed_before_comparing():
    ours = {
        "changes": [
            {"path": "docs/a.md", "old_path": None, "change_type": "ADDED", "category": "DOCUMENTATION"},
            {"path": "docs/x.md", "old_path": None, "change_type": "DELETED", "category": "DOCUMENTATION"},
            {"path": "huge.txt", "old_path": None, "change_type": "ADDED", "category": "DOCUMENTATION"},
            {"path": "logo.png", "old_path": None, "change_type": "ADDED", "category": "OTHER"},
        ],
        "skipped": [{"path": "logo.png", "reason": "UNSUPPORTED_FILE_TYPE"}],
    }
    theirs = {
        "changes": [
            {"path": ".archive/x.md", "old_path": "docs/x.md", "change_type": "RENAMED", "category": "OTHER"},
            {"path": ".github/ci.yaml", "old_path": None, "change_type": "ADDED", "category": "OTHER"},
            {"path": "docs/a.md", "old_path": ".github/a.md", "change_type": "RENAMED", "category": "OTHER"},
            {"path": "huge.txt", "old_path": None, "change_type": "ADDED", "category": "OTHER"},
            {"path": "logo.png", "old_path": None, "change_type": "ADDED", "category": "OTHER"},
        ],
        "skipped": [{"path": ".github/x.png", "reason": "UNSUPPORTED_FILE_TYPE"}, {"path": "logo.png", "reason": "UNSUPPORTED_FILE_TYPE"}],
    }
    assert reference.differences(*reference.comparable(ours, theirs)) == []
    wrong = {**theirs, "changes": [{**c, "change_type": "MODIFIED"} if c["path"] == "logo.png" else c for c in theirs["changes"]]}
    assert reference.differences(*reference.comparable(ours, wrong)) == [
        "body.changes[3].change_type: ours 'ADDED', theirs 'MODIFIED'"
    ]
