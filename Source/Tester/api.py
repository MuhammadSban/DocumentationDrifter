# serves the cross-team tester under /tester: set up a session on a target, run the shared tests, read the report

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException

from Tester import suite

app = FastAPI(
    title="DocumentationDrifter tester",
    openapi_url="/openapi.json",  # serves the document at /tester/openapi.json once mounted
    docs_url=None,
    redoc_url=None,
)


class TesterSetupRequest(BaseModel):
    # names the system to test, the URL its /test, /analyze and /analysis routes hang off, no query or fragment
    target_url: str = Field(pattern=r"^https?://[^\s?#]+$")


class TesterRunRequest(BaseModel):
    # names a session opened by POST /test/setup
    session_id: str


def tester_error(status: int, message: str, source: str = "tester") -> JSONResponse:
    # answers with the tester's error body
    return JSONResponse(status_code=status, content={"message": message, "source": source})


def _describe(error: dict) -> str:
    # words the first validation error the way a caller can act on
    loc = [part for part in error.get("loc", ()) if part != "body"]
    kind = error.get("type", "")
    if not loc or kind == "json_invalid":
        return "body is required" if kind == "missing" else "body must be a JSON object"
    field = loc[0]
    if kind == "missing":
        return f"{field} is required"
    if kind == "string_pattern_mismatch":
        return f"{field} must be an http or https URL without a query or fragment"
    return f"{field} has the wrong type"


@app.exception_handler(RequestValidationError)
def _bad_request(_: Request, exc: RequestValidationError) -> JSONResponse:
    # answers validation failures as 400, never 422
    return tester_error(400, _describe(exc.errors()[0]))


@app.exception_handler(HTTPException)
def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
    # answers an unknown route or method in the tester's error body, not FastAPI's {"detail"}
    return tester_error(exc.status_code, str(exc.detail))


@dataclass
class Session:
    # holds one session's target and, once the suite ends, its report bytes
    target_url: str
    report: bytes | None = None


class Sessions:
    # holds sessions and reports in memory, lost on restart

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def open(self, session_id: str, target_url: str) -> None:
        # keeps a session the target accepted
        with self._lock:
            self._sessions[session_id] = Session(target_url)

    def get(self, session_id: str) -> Session | None:
        # finds a session, None when it was never set up
        with self._lock:
            return self._sessions.get(session_id)

    def finish(self, session_id: str, report: bytes) -> None:
        # stores the suite report, so GET /test/report serves the same bytes
        with self._lock:
            self._sessions[session_id].report = report


SESSIONS = Sessions()


def _json(data: bytes) -> Response:
    # returns stored bytes as they are
    return Response(content=data, media_type="application/json")


@app.post("/test/setup", status_code=201)
def test_setup(request: TesterSetupRequest):
    # opens a session on the target under a fresh id, kept only once the target answered 201
    session_id = str(uuid.uuid4())
    target_url = request.target_url.rstrip("/")
    try:
        suite.setup_target(target_url, session_id)
    except suite.TargetError as exc:
        return tester_error(exc.status, exc.message, exc.source)
    SESSIONS.open(session_id, target_url)
    return {"session_id": session_id}


@app.post("/test/run")
def test_run(request: TesterRunRequest):
    # runs the shared tests on a session and returns the stored suite report
    session = SESSIONS.get(request.session_id)
    if session is None:
        return tester_error(404, f"session {request.session_id} is unknown")
    data = json.dumps(suite.run(request.session_id, session.target_url)).encode()
    SESSIONS.finish(request.session_id, data)
    return _json(data)


@app.get("/test/report")
def test_report(session_id: str | None = None):
    # serves a session's stored suite report without running anything, 409 until the suite ends
    if not session_id:
        return tester_error(400, "session_id query parameter is required")
    session = SESSIONS.get(session_id)
    if session is None:
        return tester_error(404, f"session {session_id} is unknown")
    if session.report is None:
        return tester_error(409, f"session {session_id} has no report yet, its suite hasn't ended")
    return _json(session.report)


@app.get("/", include_in_schema=False)
def index() -> dict:
    # lists the routes for a person who opens /tester/, the main app serves plain /tester with it too
    return {
        "service": "DocumentationDrifter tester",
        "routes": [
            "POST /tester/test/setup",
            "POST /tester/test/run",
            "GET /tester/test/report?session_id=...",
        ],
    }
