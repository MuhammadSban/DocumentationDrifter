# covers the tester port: the cross-team tester mounted at /tester, the system and console left exactly as they were

import json
import uuid
from pathlib import Path

import pytest

# holds /system/openapi.json paths and schemas and the GET /system body, captured from main at aba19c6
BEFORE = json.loads((Path(__file__).resolve().parent / "data" / "system-openapi-before-tester.json").read_text())
SOURCES = {"tester", "system", "communication", "unknown"}


def assert_tester_error(r, status: int):
    # checks a tester error: the status and a {message, source} body naming the tester
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) == {"message", "source"}, body
    assert isinstance(body["message"], str) and body["message"].strip()
    assert body["source"] == "tester"


# --- the system stays as it was --------------------------------------


def test_system_openapi_paths_are_unchanged(api):
    assert api.get("/system/openapi.json").json()["paths"] == BEFORE["paths"]


def test_system_openapi_schemas_are_unchanged(api):
    assert api.get("/system/openapi.json").json()["components"]["schemas"] == BEFORE["schemas"]


def test_system_index_is_unchanged(api):
    r = api.get("/system")
    assert r.status_code == 200
    assert r.json() == BEFORE["index"]


@pytest.mark.parametrize("path", ["/", "/system/docs", "/system/health"])
def test_console_docs_and_health_still_answer(api, path):
    assert api.get(path).status_code == 200


def test_tester_routes_stay_out_of_the_system_openapi(api):
    paths = api.get("/system/openapi.json").json()["paths"]
    assert not [p for p in paths if p.startswith("/tester") or not p.startswith("/system/")]


# --- the tester is reachable -----------------------------------------


def test_tester_index_lists_the_three_routes(api):
    r = api.get("/tester")
    assert r.status_code == 200, r.text
    routes = " ".join(r.json()["routes"])
    for route in ("POST /tester/test/setup", "POST /tester/test/run", "GET /tester/test/report"):
        assert route in routes


def test_tester_docs_answer(api):
    r = api.get("/tester/docs")
    assert r.status_code == 200
    assert "swagger" in r.text.lower()


def test_tester_openapi_lists_its_three_operations(api):
    r = api.get("/tester/openapi.json")
    assert r.status_code == 200, r.text
    paths = r.json()["paths"]
    assert set(paths) == {"/test/setup", "/test/run", "/test/report"}
    assert "post" in paths["/test/setup"] and "post" in paths["/test/run"] and "get" in paths["/test/report"]


# --- the tester refuses what it can't use ----------------------------


@pytest.mark.parametrize("body", [{}, {"target_url": ""}, {"target_url": 5}, {"other": "x"}])
def test_setup_without_a_target_url_is_400(api, body):
    assert_tester_error(api.post("/tester/test/setup", json=body), 400)


def test_setup_with_a_non_object_body_is_400(api):
    assert_tester_error(api.post("/tester/test/setup", content=b"[1]", headers={"content-type": "application/json"}), 400)


# uses .invalid hosts, so a URL let through by mistake fails fast instead of reaching a real service
@pytest.mark.parametrize("url", [
    "not a url",
    "ftp://team.invalid/system",
    "https://user:secret@team.invalid/system",
    "https://team.invalid/system?x=1",
    "https://team.invalid/system#top",
])
def test_setup_with_a_bad_target_url_is_400(api, url):
    assert_tester_error(api.post("/tester/test/setup", json={"target_url": url}), 400)


def test_run_without_a_session_id_is_400(api):
    assert_tester_error(api.post("/tester/test/run", json={}), 400)


def test_run_of_an_unknown_session_is_404(api):
    assert_tester_error(api.post("/tester/test/run", json={"session_id": f"none-{uuid.uuid4().hex}"}), 404)


def test_report_without_a_session_id_is_400(api):
    assert_tester_error(api.get("/tester/test/report"), 400)


def test_report_of_an_unknown_session_is_404(api):
    assert_tester_error(api.get("/tester/test/report", params={"session_id": f"none-{uuid.uuid4().hex}"}), 404)
