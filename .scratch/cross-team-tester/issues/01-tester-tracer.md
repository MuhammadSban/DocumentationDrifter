# 01: Tester tracer: setup, run and report end to end with one test

**What to build:** A tester at `/tester` in the same app as `/system`, that a grader can point at any team's system. `POST /tester/test/setup {"target_url"}` makes a fresh UUID, calls the target's `POST {target_url}/test/setup {"session_id", "setup": {}}`, and answers 201 `{"session_id"}` only once the target answered 201; if the target's setup fails, it answers with the target's status, message and source, and no runnable session is kept. `POST /tester/test/run {"session_id"}` runs the shared test list (for this ticket, only T-15: an unknown `analysis_id` gives 404 `ANALYSIS_NOT_FOUND`), then reads `GET {target_url}/test/report?session_id=` and returns the suite report: `{"session_id", "target_url", "results": [{"test_id", "outcome", "message", "source"?}], "coverage": {"code", "component", "system"}}`. `GET /tester/test/report?session_id=` returns the stored report without running anything, or 409 before the suite ends. Every tester error is `{"message", "source"}`: 400 invalid request, 404 unknown session, 409 conflict or not ready, 500 abort or failure, with source `tester`, `system`, `communication` or `unknown`. Sessions and reports live in memory until the process restarts. Component and system coverage may be `null` counts with a `basis` saying why until ticket 04.

**Blocked by:** None (can start immediately)

**Status:** ready-for-human · implemented (2026-10-18), not yet deployed. The tester is its own package, `Source/Tester/` (outside `GitHub_Connector`, so the course coverage count of `/system` leaves it out), mounted as a separate FastAPI app at `/tester`; plain `/tester` is a route on the main app, since the mount only matches paths under `/tester/`. Every target call goes through `suite.client()`, which the tests swap for a `TestClient` on the in-process app or an `httpx.MockTransport` stub; 31 tests in `tests/test_tester_tracer.py`. A target `coverage.code` lacking `covered` or `total` counts as missing. A URL httpx can't parse (`http://a:x`) is 400 `tester`. Left for later tickets: 409 on a repeated run, aborts and tester-failure 500s (05). Open: `target_url` is unrestricted, so the tester will call any host, internal ones included (SSRF); not decided. Decided on 2026-10-18 (TT-Q2 to TT-Q6).

**Spec:** docs/plan/decisions.md, "The cross-team tester, 2026-10-18"; the course's "Cross-team Testing Interface" (student-facing spec); CONTEXT.md, "Cross-team testing"

- [x] The three routes are served under `/tester` by the same app, with their own OpenAPI document at `/tester/openapi.json`, and `/system`'s OpenAPI document is unchanged.
- [x] `GET /tester` lists the tester's routes, as `GET /system` does.
- [x] Setup generates a new UUID every time, forwards it with `setup: {}`, and returns 201 with the same id only after the target's 201.
- [x] A target setup that fails is passed back with its status, message and source, and that id can't be run; a target that can't be reached gives 500 with source `communication`.
- [x] A missing or malformed body gives 400 with source `tester`; an unknown session id gives 404.
- [x] A run returns 200 with every planned test exactly once, each with a unique non-empty `test_id` and a non-empty `message`; an `error` result carries a `source`.
- [x] `coverage.code` is copied from the target's report; a target report that fails or lacks the field gives `null` counts and a `basis` saying why, never zero.
- [x] `GET /tester/test/report` returns the stored body unchanged, 409 before the suite ends, 404 for an unknown session.
- [x] The tester reaches every target only over HTTP at `target_url`, so tests run it against the in-process `/system` and against a stub target.
- [x] `docs/spec.md` gains a "Tester" section, and the README names the tester URL.
- [x] The whole suite is green offline.
