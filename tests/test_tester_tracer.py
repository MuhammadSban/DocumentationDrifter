# covers cross-team tester ticket 01: setup, run and report under /tester, against the in-process /system and stub targets

import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

SYSTEM = "http://testserver/system"
STUB = "http://stub.test/system"


@pytest.fixture
def tester(api, monkeypatch):
    # points the tester's target calls at the in-process app, still over HTTP
    from GitHub_Connector.api import app
    from Tester import suite

    monkeypatch.setattr(suite, "client", lambda: TestClient(app))
    return api


@pytest.fixture
def stub(api, monkeypatch):
    # points the tester's target calls at a stub target, returns the dict of handlers to fill and the calls seen
    from Tester import suite

    routes: dict[tuple[str, str], object] = {}
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        path = request.url.path.removeprefix("/system")
        key = (request.method, "/analysis/*" if path.startswith("/analysis/") else path)
        answer = routes.get(key)
        if answer is None:
            return httpx.Response(404, json={"message": "no stub route", "source": "system"})
        return answer(request) if callable(answer) else answer

    monkeypatch.setattr(suite, "client", lambda: httpx.Client(transport=httpx.MockTransport(handle)))
    return routes, calls


def healthy(routes):
    # fills a stub with a target that behaves like a correct system
    routes[("POST", "/test/setup")] = lambda r: httpx.Response(201, json={"session_id": json.loads(r.content)["session_id"]})
    routes[("GET", "/analysis/*")] = httpx.Response(404, json={"code": "ANALYSIS_NOT_FOUND", "message": "gone"})
    code = {"covered": 3, "total": 10, "basis": "stub lines"}
    routes[("GET", "/test/report")] = lambda r: httpx.Response(
        200, json={"session_id": r.url.params["session_id"], "coverage": {"code": code}}
    )


def setup(api, target_url=SYSTEM):
    # opens a tester session against target_url
    return api.post("/tester/test/setup", json={"target_url": target_url})


def run(api, session_id):
    # runs the suite on an open session
    return api.post("/tester/test/run", json={"session_id": session_id})


def assert_error(r, status, source):
    # checks the tester's error body, a non-empty message and the given source
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) == {"message", "source"} and body["message"] and body["source"] == source


# --- routes and documents --------------------------------------------


def test_the_tester_has_its_own_openapi_document(tester):
    doc = tester.get("/tester/openapi.json").json()
    assert set(doc["paths"]) == {"/test/setup", "/test/run", "/test/report"}
    system = tester.get("/system/openapi.json").json()
    assert not any("tester" in p or p.endswith("/test/run") for p in system["paths"])


@pytest.mark.parametrize("path", ["/tester", "/tester/"])
def test_plain_tester_lists_its_routes(tester, path):
    r = tester.get(path, follow_redirects=False)
    assert r.status_code == 200
    assert r.json()["routes"] == [
        "POST /tester/test/setup",
        "POST /tester/test/run",
        "GET /tester/test/report?session_id=...",
    ]


@pytest.mark.parametrize("method, path, status", [("GET", "/tester/nope", 404), ("GET", "/tester/test/setup", 405)])
def test_unknown_tester_routes_answer_in_the_tester_error_shape(tester, method, path, status):
    assert_error(tester.request(method, path), status, "tester")


# --- setup -----------------------------------------------------------


def test_setup_against_our_system_returns_a_fresh_uuid(tester):
    first, second = setup(tester), setup(tester)
    assert first.status_code == 201, first.text
    ids = [first.json()["session_id"], second.json()["session_id"]]
    assert all(str(uuid.UUID(i)) == i for i in ids) and ids[0] != ids[1]
    assert list(first.json()) == ["session_id"]


def test_setup_forwards_the_id_with_an_empty_setup(stub, api):
    routes, calls = stub
    healthy(routes)
    r = setup(api, STUB + "/")
    assert r.status_code == 201
    assert str(calls[0].url) == STUB + "/test/setup"
    assert json.loads(calls[0].content) == {"session_id": r.json()["session_id"], "setup": {}}


def test_a_failed_target_setup_is_passed_back_and_not_runnable(stub, api):
    routes, calls = stub
    routes[("POST", "/test/setup")] = httpx.Response(409, json={"message": "taken", "source": "system"})
    r = setup(api, STUB)
    assert r.status_code == 409 and r.json() == {"message": "taken", "source": "system"}
    sid = json.loads(calls[0].content)["session_id"]
    assert_error(run(api, sid), 404, "tester")


@pytest.mark.parametrize("body", [{"message": "odd", "source": "whatever"}, {"message": "odd"}, "plain"])
def test_a_target_source_outside_the_four_is_unknown(stub, api, body):
    routes, _ = stub
    answer = httpx.Response(400, json=body) if isinstance(body, dict) else httpx.Response(400, text=body)
    routes[("POST", "/test/setup")] = answer
    assert_error(setup(api, STUB), 400, "unknown")


def test_a_target_setup_answering_200_is_a_500(stub, api):
    routes, _ = stub
    routes[("POST", "/test/setup")] = httpx.Response(200, json={"session_id": "x"})
    assert_error(setup(api, STUB), 500, "unknown")


def test_an_unreachable_target_is_a_communication_error(stub, api):
    routes, _ = stub

    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    routes[("POST", "/test/setup")] = refuse
    assert_error(setup(api, STUB), 500, "communication")


@pytest.mark.parametrize(
    "body",
    [None, [1], {}, {"target_url": 7}, {"target_url": "not a url"},
     {"target_url": "http://x/system?a=1"}, {"target_url": "http://x/system#top"}],
)
def test_setup_rejects_a_missing_or_malformed_body(tester, body):
    r = tester.post("/tester/test/setup") if body is None else tester.post("/tester/test/setup", json=body)
    assert_error(r, 400, "tester")


def test_setup_rejects_a_url_httpx_cannot_parse(stub, api):
    assert_error(setup(api, "http://a:x"), 400, "tester")


def test_setup_rejects_a_body_that_is_not_json(tester):
    r = tester.post("/tester/test/setup", content=b"{", headers={"content-type": "application/json"})
    assert_error(r, 400, "tester")
    assert r.json()["message"] == "body must be a JSON object"


# --- run -------------------------------------------------------------


def test_a_run_against_our_system_passes_t15_and_copies_code_coverage(tester):
    sid = setup(tester).json()["session_id"]
    r = run(tester, sid)
    assert r.status_code == 200, r.text
    body = r.json()
    assert list(body) == ["session_id", "target_url", "results", "coverage"]
    assert body["session_id"] == sid and body["target_url"] == SYSTEM
    assert [x["test_id"] for x in body["results"]] == ["T-15"]
    t15 = body["results"][0]
    assert t15["outcome"] == "pass" and t15["message"] and "source" not in t15
    code = body["coverage"]["code"]
    assert isinstance(code["covered"], int) and 0 < code["covered"] <= code["total"] and "GitHub_Connector" in code["basis"]


def test_component_and_system_coverage_are_null_with_a_reason(tester):
    sid = setup(tester).json()["session_id"]
    coverage = run(tester, sid).json()["coverage"]
    for name in ("component", "system"):
        assert coverage[name]["covered"] is None and coverage[name]["total"] is None and coverage[name]["basis"]


@pytest.mark.parametrize(
    "answer, outcome, source",
    [
        (httpx.Response(404, json={"code": "ANALYSIS_NOT_FOUND", "message": "gone"}), "pass", None),
        (httpx.Response(200, json={"analysis_id": "an-x"}), "fail", None),
        (httpx.Response(404, json={"code": "OTHER", "message": "x"}), "fail", None),
        (httpx.Response(404, text="plain"), "fail", None),
        (httpx.Response(503, text="down"), "error", "system"),
    ],
)
def test_t15_is_judged_on_status_and_code(stub, api, answer, outcome, source):
    routes, _ = stub
    healthy(routes)
    routes[("GET", "/analysis/*")] = answer
    sid = setup(api, STUB).json()["session_id"]
    t15 = run(api, sid).json()["results"][0]
    assert t15["outcome"] == outcome and t15["message"]
    assert t15.get("source") == source


def test_t15_with_no_response_is_a_communication_error(stub, api):
    routes, _ = stub
    healthy(routes)

    def hang(request):
        raise httpx.ReadTimeout("slow", request=request)

    routes[("GET", "/analysis/*")] = hang
    sid = setup(api, STUB).json()["session_id"]
    t15 = run(api, sid).json()["results"][0]
    assert t15["outcome"] == "error" and t15["source"] == "communication"


def test_code_coverage_is_copied_from_the_target_report(stub, api):
    routes, calls = stub
    healthy(routes)
    sid = setup(api, STUB).json()["session_id"]
    body = run(api, sid).json()
    assert body["coverage"]["code"] == {"covered": 3, "total": 10, "basis": "stub lines"}
    assert calls[-1].url.params["session_id"] == sid


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(500, json={"message": "broke", "source": "system"}),
        httpx.Response(200, json={"session_id": "x", "coverage": {}}),
        httpx.Response(200, json={"session_id": "x", "coverage": None}),
        httpx.Response(200, json={"session_id": "x", "coverage": {"code": {}}}),
        httpx.Response(200, json={"session_id": "x", "coverage": {"code": {"covered": 1}}}),
        httpx.Response(200, text="not json"),
    ],
)
def test_a_failed_or_partial_target_report_gives_null_code_counts(stub, api, answer):
    routes, _ = stub
    healthy(routes)
    routes[("GET", "/test/report")] = answer
    sid = setup(api, STUB).json()["session_id"]
    code = run(api, sid).json()["coverage"]["code"]
    assert code["covered"] is None and code["total"] is None and code["basis"]


def test_run_rejects_an_unknown_session_and_a_malformed_body(tester):
    assert_error(run(tester, str(uuid.uuid4())), 404, "tester")
    assert_error(tester.post("/tester/test/run", json={}), 400, "tester")
    assert_error(tester.post("/tester/test/run"), 400, "tester")


# --- report ----------------------------------------------------------


def test_the_report_is_409_before_the_run_and_the_stored_body_after(tester):
    sid = setup(tester).json()["session_id"]
    assert_error(tester.get("/tester/test/report", params={"session_id": sid}), 409, "tester")
    ran = run(tester, sid)
    stored = tester.get("/tester/test/report", params={"session_id": sid})
    assert stored.status_code == 200 and stored.content == ran.content


def test_the_report_needs_a_known_session(tester):
    assert_error(tester.get("/tester/test/report"), 400, "tester")
    assert_error(tester.get("/tester/test/report", params={"session_id": "nope"}), 404, "tester")
