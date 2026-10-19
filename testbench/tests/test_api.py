# checks our deployed HTTP contract without depending on the reference service

import re
import uuid
from datetime import datetime

import httpx
import pytest

pytestmark = pytest.mark.website


def test_health_and_route_list(website_client):
    response = website_client.get("system/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "storage": "local"}
    response = website_client.get("system")
    assert response.status_code == 200
    assert "POST /system/analyze" in response.json()["routes"]


def test_openapi_exposes_our_routes_and_team_16s_categories(website_client):
    response = website_client.get("system/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert {"/system/analyze", "/system/analysis/{analysis_id}", "/system/health", "/system/test/setup", "/system/test/report"} <= set(schema["paths"])
    # lists Team 16's six categories, DOCUMENTATION left the contract in cross-team ticket 07
    assert set(schema["components"]["schemas"]["Category"]["enum"]) == {
        "REQUIREMENT", "SPECIFICATION", "ARCHITECTURE", "DESIGN", "IMPLEMENTATION", "OTHER"
    }


@pytest.mark.parametrize("body,message", [
    ({"repository": "octo/demo"}, "commit_id is required"),
    ({"commit_id": "a" * 40}, "repository is required"),
    ({"repository": "bad-repository", "commit_id": "a" * 40}, "repository must use the format owner/name"),
    ({"repository": "octo/demo", "commit_id": "not-hex"}, "commit_id must be a 7-40 character hexadecimal commit SHA"),
    ({"repository": "octo/demo", "commit_id": "a" * 40, "base_commit": "bad"}, "base_commit must be a 7-40 character hexadecimal commit SHA"),
    ({"repository": 7, "commit_id": "a" * 40}, "repository has the wrong type"),
], ids=["missing-head", "missing-repository", "bad-repository", "bad-head", "bad-base", "wrong-type"])
def test_invalid_analysis_returns_actionable_json(website_client, body, message):
    response = website_client.post("system/analyze", json=body)
    assert response.status_code == 400, response.text
    assert response.json() == {"code": "INVALID_REQUEST", "message": message}


def test_malformed_json_is_rejected(website_client):
    response = website_client.post("system/analyze", content="{broken", headers={"Content-Type": "application/json"})
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"


@pytest.mark.parametrize("analysis_id", ["an-" + "0" * 32, "not-a-run", "..%2F..%2Fsecret"])
def test_unknown_or_unsafe_run_returns_no_file(website_client, analysis_id):
    response = website_client.get("system/analysis/" + analysis_id)
    assert response.status_code == 404
    assert response.json()["code"] == "ANALYSIS_NOT_FOUND"


@pytest.mark.parametrize("label", ["root", "modified", "added-and-deleted", "renamed", "docs-category", "hidden-paths", "binary", "oversize", "non-utf8", "many-files", "mixed", "base-equals-head", "explicit-base-range", "short-sha", "unknown-commit"])
def test_fixture_analysis_and_saved_run(website_client, website_cases, pytestconfig, label):
    repository, labels = website_cases
    case = labels[label]
    try:
        response = website_client.post("system/analyze", json={"repository": repository, **case["request"]})
    except httpx.TimeoutException:
        pytest.fail(f"{label}: /system/analyze did not answer within the 180-second HTTP timeout", pytrace=False)
    expected = case["expect"]
    assert response.status_code == expected["status"], response.text
    body = response.json()
    if expected["status"] != 200:
        assert body["code"] == expected["code"]
        return
    assert body["repository"] == repository
    assert body["status"] == "SUCCESS" and body["error"] is None
    assert isinstance(body["issues"], list)
    if not pytestconfig.getoption("--website-url"):
        assert body["issues"] == [], "The local bench uses a no-findings LLM test double"
    else:
        # checks hosted findings without assuming a live model always reports no drift
        changes = {change["path"]: change["category"] for change in body["changes"]}
        for finding in body["issues"]:
            assert finding["code_file"] in changes
            assert finding["change_category"] == changes[finding["code_file"]]
            assert finding["issue_type"] in {"OUTDATED_DOCUMENTATION", "MISSING_DOCUMENTATION"}
            assert finding["verification_status"] == "PENDING_REVIEW"
            for field in ("finding_id", "code_file", "explanation"):
                assert isinstance(finding[field], str) and finding[field]
            assert finding["documentation_file"] is None or isinstance(finding["documentation_file"], str)
    assert re.fullmatch(r"an-[0-9a-f]{32}", body["analysis_id"])
    assert re.fullmatch(r"[0-9a-f]{40}", body["head_commit"])
    assert body["config_version"] and body["tool_version"]
    assert datetime.fromisoformat(body["created_at"].replace("Z", "+00:00")).utcoffset().total_seconds() == 0
    for key in ("head_commit", "base_commit", "changes", "skipped"):
        assert body[key] == expected[key], f"{label}: {key} differs"
    saved = website_client.get("system/analysis/" + body["analysis_id"])
    assert saved.status_code == 200
    assert saved.content == response.content


def test_course_session_setup_duplicate_and_report(website_client):
    sid = "website-" + uuid.uuid4().hex
    response = website_client.post("system/test/setup", json={"session_id": sid, "setup": {}})
    assert response.status_code == 201
    assert response.json() == {"session_id": sid}
    response = website_client.post("system/test/setup", json={"session_id": sid})
    assert response.status_code == 409
    assert response.json() == {"message": f"session {sid} already exists", "source": "system"}
    response = website_client.get("system/test/report", params={"session_id": sid})
    assert response.status_code == 200
    assert response.json()["session_id"] == sid
    counts = response.json()["coverage"]["code"]
    assert 0 <= counts["covered"] <= counts["total"] and counts["total"] > 0
    assert counts["basis"]


def test_course_errors_use_their_own_error_shape(website_client):
    response = website_client.get("system/test/report")
    assert response.status_code == 400
    assert response.json() == {"message": "session_id query parameter is required", "source": "system"}
    response = website_client.get("system/test/report", params={"session_id": uuid.uuid4().hex})
    assert response.status_code == 404
    assert response.json()["source"] == "system"
