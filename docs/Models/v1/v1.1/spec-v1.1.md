# Spec: v1.1 change detection API

Status: **done**, v1.1 is built and deployed. · Written 2026-10-17 from the [roadmap](../../../plan/roadmap.md) v1 section and the [decision log](../../../plan/decisions.md). Terms are as defined in [CONTEXT.md](../../../../CONTEXT.md).

**Amended 2026-10-17 by the ticket 12 grilling** (decision log, T12-Q1 to T12-Q5). Where a story or decision below is marked *Amended*, the decision log wins: skipped files stay in `changes[]`, skips are by file type first with code reasons, and `tool_version` carries the build. Hidden paths stay ignored (T12-Q8, T12-Q9).

## Problem Statement

The course tester and, later, a GitHub Action need to ask our service "what changed between these two commits of this public repo, and what kind of file is each change?" Today the repo has only the v0 webhook receiver, which records commit pairs and answers nothing. The reference service already answers this question with a fixed contract, and both teams are graded against the same tester. So any analysis we can't run, or any answer that differs from the reference service, is a failed test, and so is a failure that looks like a success.

## Solution

A small FastAPI service under `/system` that matches the reference service's contract. A caller posts a repository, a head commit and an optional base commit. The service clones the repo anonymously with git, works out every changed file and its change type, gives each a category from path rules, and saves the result once as a run file. It returns the result and serves the same bytes back by `analysis_id`. Bad input and failed checks return an error and save nothing. `issues[]` is always empty in v1.1; v1.2 fills it with an LLM.

## User Stories

1. As the course tester, I want `POST /system/analyze` to accept `repository`, `commit_id` and an optional `base_commit`, so that I can drive our service with the same requests I send the reference service.
2. As the course tester, I want the response to carry all twelve `AnalysisResult` fields, so that my schema checks pass.
3. As the course tester, I want `analysis_id` to be `an-` followed by 32 hex characters, so that it has the same format as the reference service's.
4. As the course tester, I want `created_at` in ISO 8601 UTC with milliseconds and a `Z`, so that timestamps parse the same on both services.
5. As the course tester, I want `config_version` to always be a string, so that a null never breaks my checks.
6. As the course tester, I want `tool_version` in every result, so that I can tell which build produced a run.
7. As the course tester, I want `GET /system/analysis/{id}` to return the saved run byte for byte, so that the evidence can't drift after the fact (AC-06, T-05).
8. As the course tester, I want an unknown `analysis_id` to return 404, so that a missing run is never confused with an empty one.
9. As the course tester, I want `GET /system/health`, so that I can wake the service before a test run.
10. As the course tester, I want a missing `commit_id` to return 400 `INVALID_REQUEST` with "commit_id is required", so that AC-07 passes.
11. As the course tester, I want a badly formed `repository` to return 400 `INVALID_REQUEST`, so that bad input fails before any network call.
12. As the course tester, I want a `commit_id` or `base_commit` that isn't 7–40 hex characters to return 400 `INVALID_REQUEST`, so that garbage never reaches git.
13. As the course tester, I want FastAPI's own validation errors to come back as 400 `INVALID_REQUEST` rather than 422, so that error codes match the reference service.
14. As the course tester, I want a missing or private repository to return 404 `REPOSITORY_NOT_FOUND`, so that private repos are never read, even where the host has GitHub credentials.
15. As the course tester, I want an unknown commit to return 404 `COMMIT_NOT_FOUND`, so that AC-08 passes.
16. As a caller using a short SHA, I want it expanded to the full 40-character SHA in `head_commit` and `base_commit`, so that the run names exact commits.
17. As a caller using a short SHA that can't be fetched or is ambiguous, I want 404 `COMMIT_NOT_FOUND` with a message asking for the full SHA, so that I know how to fix my request.
18. As a caller who leaves out `base_commit`, I want the head's first parent used as the base, so that a single commit is analysed by default.
19. As a caller analysing a root commit, I want `base_commit` to be `null` and every file to be ADDED, so that a first audit lists the whole tree.
20. As a caller who gives an explicit `base_commit`, I want exactly that diff, even when the base equals, follows or is unrelated to the head, so that the API stays predictable.
21. As a caller whose base equals the head, I want SUCCESS with an empty `changes[]`, so that "nothing changed" is a valid answer.
22. As the course tester, I want each changed file listed once with ADDED, MODIFIED, DELETED or RENAMED, so that T-01, T-02, T-06 and T-07 pass.
23. As the course tester, I want a rename reported as one RENAMED change with `old_path` set, not as a delete plus an add, so that T-03 passes.
24. As a maintainer, I want renames detected at git's default 50% similarity and copies never reported, so that our output agrees with the reference service.
25. As a caller, I want hidden paths (any segment starting with `.`) left out of `changes[]` entirely, so that tooling files like `.gitignore` and `.github/` never show up, and symlinks and submodules listed in `changes[]` and skipped as `UNSUPPORTED_FILE_TYPE`, since they are never read, as the reference does (T12-Q10, ticket 17). A switch between a regular file and a symlink or submodule is one TYPE_CHANGED change and isn't skipped.
26. As a caller, I want a rename out of a hidden path reported as ADDED, and a rename into one as DELETED, so that a hidden path never appears, not even as `old_path`.
27. As a caller, I want every change to have a category from the path rules, so that I can tell code changes from doc changes.
28. As the course tester, I want `docs/**`, `*.md`, `*.rst` and `*.txt` classified as DOCUMENTATION, so that T-04 passes.
29. As a maintainer, I want `requirements*.txt` classified as OTHER ahead of the `*.txt` rule, so that dependency lists aren't counted as docs.
30. As a maintainer, I want `src/**`, `tests/**`, `*.py` and `*.sh` classified as IMPLEMENTATION and everything else as OTHER, so that the first matching rule gives one clear answer.
31. As a maintainer, I want the path rules in one config file, and `config_version` to be a short hash of it, so that a change to the rules shows up in every run.
32. *Amended by T12-Q1 and T12-Q2: skipped files stay in `changes[]`, and reasons are codes.* As a caller, I want binary files and files over 1 MB listed in `skipped[]` with a reason, so that I know they weren't checked.
33. *Amended by T12-Q2: reason code `NOT_UTF8`.* As a caller, I want changed files that aren't valid UTF-8 listed in `skipped[]` with a reason, so that nothing unread is reported as checked.
34. As a caller, I want `changes[]` and `skipped[]` sorted by path, so that repeated runs compare cleanly.
35. As the course tester, I want three identical requests to give results that differ only in `analysis_id` and `created_at`, so that AC-10 passes without its confidence clause.
36. As the course tester, I want more than 300 changed files all returned, so that large commits aren't silently cut short.
37. As the course tester, I want `issues[]` present and empty in v1.1, so that the shape is right before v1.2 fills it.
38. As a maintainer, I want a failed analysis to return an `ErrorBody` with 400, 404 or 500 and save no run file, so that a failure never looks like a SUCCESS run.
39. As a maintainer, I want each git call capped at 60 s and the whole analysis at 120 s, both returning 500 `TIMEOUT`, so that a slow repo can't hang the service.
40. As a maintainer, I want at most two analyses to run at once, with extra requests waiting, so that two blobless clones fit in the 0.5 GB of Railway's free plan.
41. As a maintainer, I want the deadline, git timeout and concurrency limit in config, so that I can tune them without changing code.
42. As a maintainer, I want a failure to write the run file to return 500 `WRITE_FAILED`, so that a lost run is never reported as saved.
43. As the analysed repo's owner, I want the service never to install, import or run my code, and never to write my files to disk except as git objects in a temporary clone, so that analysing my repo is safe.
44. As a maintainer, I want the temporary clone deleted after every analysis, error or not, so that the disk doesn't fill up.
45. As the analysed repo's owner, I want my repository left unchanged by an analysis (AC-09), so that the tool stays read-only.
46. As a maintainer, I want the run store to sit behind one module with `save`, `load` and `dump`, so that v3 can swap local disk for a durable store in one place.
47. As a maintainer, I want the connector used as a scope (`with fetch(...) as cmp:`) with `tree()` and `read()` available inside it, so that v1.2 can read files for the LLM without reworking the connector.
48. As a maintainer, I want `analyze()` callable directly, without HTTP, so that the v3 Action and the v4 webhook can reuse it.
49. As a maintainer, I want a conformance test that sends the same requests to the reference service and to ours and compares the results, so that any difference shows up as a failing test.
50. As a maintainer, I want the conformance test to treat the DOCUMENTATION category and `config_version` as the only known differences, so that real regressions stand out.
51. As a maintainer, I want the conformance and network tests skipped when offline, so that the local suite always runs.
52. As a maintainer, I want the v0 webhook tests to keep passing and the v1 app never to import v0's app, so that v0 stays intact for v4.
53. As a maintainer, I want CI to run the test suite on every PR, so that a red change can't merge unnoticed.
54. As a maintainer, I want a manual acceptance workflow that warms the deployed service and runs T-01 to T-07 and the conformance test against it, so that the deployed URL is checked the same way the tester will check it.
55. As the course tester, I want the service deployed at a public URL, so that I can reach it.
56. As an operator, I want the README to say that the free service sleeps when idle and loses saved runs on redeploy and restart, so that a 404 on an old run isn't mistaken for a bug.
57. As the course tester, I want `POST /system/test/setup` and `GET /system/test/report` with the reference service's shapes, and an unknown session to return 404 `{"message", "source":"system"}`, so that the course endpoints are graded the same on both services.
58. As a teammate, I want a public test repo with labelled cases, so that the acceptance criteria and v2's reliability run have shared fixtures.

## Implementation Decisions

- **One new FastAPI app, separate from v0.** Every contract route is on a `/system` router; the only other route is `GET /`, which serves the console and is left out of the OpenAPI document (ticket 18). The OpenAPI document is served at `/system/openapi.json`, and Swagger UI at `/system/docs`, also left out of the OpenAPI document (amended 2026-10-25, see the [decision log](../../../plan/decisions.md)); ReDoc stays off. There is no lifespan. Handlers are plain `def` and only call `analyze()`. The v0 webhook app is not served or imported.
- **Modules.** v1.1 adds seven modules beside the v0 files, with names that don't reuse v0's: the API (app and routes), the analysis (`analyze()`), the connector, the path rules plus their rules file, the run store, the API schemas, and the settings. Dataclasses are used inside the connector, and Pydantic only for the API models and the settings, which read `DRIFTER_*` environment variables with pydantic-settings as v0's config does.
- **`analyze(request) -> AnalysisResult`** is the single entry point. It raises `AnalysisError(code, message)`, and the route maps the code to 400, 404 or 500 with an `ErrorBody`. A validation handler turns FastAPI's 422 into 400 `INVALID_REQUEST`.
- **API contract.** The schemas for `AnalysisRequest`, `AnalysisResult`, `Change`, `Finding`, `Skipped` and `ErrorBody` copy the reference service's OpenAPI field for field. The only change is that DOCUMENTATION is added to the category enum used by `Change.category` and `Finding.change_category`. Error codes are INVALID_REQUEST, REPOSITORY_NOT_FOUND, COMMIT_NOT_FOUND, TIMEOUT and WRITE_FAILED. `LLM_UNAVAILABLE` arrives with v1.2. *Amended 2026-10-25: any unforeseen exception answers 500 `INTERNAL_ERROR` with an `ErrorBody` (decision log).*
- **Validation runs before any network call.** `repository` must match `owner/name` (`^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$`). `commit_id` is required and must be 7–40 hex characters, and `base_commit` follows the same rule when it is given.
- **Connector interface.** `fetch(repo, head, base)` is a context manager that yields a comparison exposing the resolved head and base, `changes`, `skipped`, `tree(side)` and `read(path, side)`. It is the only code that runs git. The clone is deleted when the scope exits.
- **Git, anonymously.** The service uses the git CLI through `subprocess`, with `GIT_TERMINAL_PROMPT=0` and an empty credential helper. It makes a blobless, no-checkout clone into a fresh temporary directory. The remote base URL is a config value: it defaults to `https://github.com/`, and tests point it at local bare repos.
- **Commit resolution.** The service fetches the head by SHA when it isn't in the clone, then runs `rev-parse --verify` to get the full SHA. The base is `base_commit` when given, otherwise the first parent, otherwise `null` for a root commit. Any base is accepted as given. A short SHA that can't be fetched or is ambiguous gives `COMMIT_NOT_FOUND`, with a message asking for the full SHA.
- **Change listing.** The service runs `git diff --name-status -M` between base and head (or the empty tree for a first audit). It reports renames only, never copies. A rename is one RENAMED change with `old_path` set. There are no hunks and no `-U0`.
- **Ignored paths.** Only regular files (modes 100644 and 100755) are kept, and any path with a segment starting with `.` is dropped. Each side of a rename is checked on its own, so a hidden `old_path` turns the change into ADDED and a hidden new path turns it into DELETED. `ls-tree` runs without `-l`.
- **Skipped files.** *Amended by T12-Q1 and T12-Q2: the extension denylist (`UNSUPPORTED_FILE_TYPE`) runs first, reasons are `BINARY_FILE`, `FILE_TOO_LARGE` and `NOT_UTF8`, and a skipped file stays in `changes[]`.* These checks run only on changed paths, after one batched `--numstat` call fetches their blobs. A file is binary if git marks it `-` or its first 8 KB contain a NUL byte. Files over 1 MB and files that aren't valid UTF-8 are also skipped, each with a reason.
- **Categories.** The first matching rule wins: `requirements*.txt` → OTHER; `docs/**`, `*.md`, `*.rst`, `*.txt` → DOCUMENTATION; `src/**`, `tests/**`, `*.py`, `*.sh` → IMPLEMENTATION (`*.sh` from T12-Q11); everything else → OTHER. There are no DESIGN, ARCHITECTURE, SPECIFICATION or REQUIREMENT rules yet. Lockfiles are classified by path (OTHER) and also skipped as `UNSUPPORTED_FILE_TYPE` (T12-Q2). `config_version` is a short hash of the rules file.
- **Run store.** It has `save(analysis_id, data)`, `load(analysis_id)` and `dump(result)`, the only serializer. Runs are written once to `runs/{analysis_id}.json` on local disk, and `runs/` is gitignored. `changes[]` and `skipped[]` are sorted by path before saving. Nothing is saved for a failed analysis.
- **Limits.** Each git call times out after 60 s and the whole analysis after 120 s, both returning `TIMEOUT`. At most two analyses run at once, using a semaphore around `analyze()`. All three values are config.
- **Hosting.** A Docker image with git installed runs uvicorn with `Source/` as the app directory. It is deployed to Railway's free plan (decision 8, 2026-10-17), and `GET /system/health` is the warm-up call and health check.
- **CI.** A PR workflow runs `python -m pytest -q` with read-only permissions, network and conformance tests included (Kaan, 2026-10-17). It warms the reference service through its health endpoint first. A manual acceptance workflow warms the deployed service with retries, then runs T-01 to T-07 and the conformance test against it.
- **Course endpoints.** `POST /system/test/setup` and `GET /system/test/report` come last and match the reference service's shapes. Their exact semantics are to be confirmed with the pod before work starts.

## Testing Decisions

- **One seam: the `/system` HTTP API** (decided by Kaan, 2026-10-17). Tests send real requests through FastAPI's TestClient and assert only on the response body, the status code and what `GET` returns. They don't test the connector, the rules or the run store directly, so those can be refactored freely. One test calls `analyze()` directly to prove it works without HTTP.
- **A good test** builds a tiny fixture repo, makes a request and checks the observable result. It never asserts on git commands, temporary paths or internal types.
- **Fixture repos.** Each test builds a bare repo with `git init` under `tmp_path / "repo"` (v0's autouse fixture writes `test.db` into `tmp_path`). The configurable remote base URL makes `owner/name` resolve to it. The fixture uses a name other than `client`, which v0 already uses.
- **Cases** (the guide's connector tests, run through the API):
  1. One modified file gives one MODIFIED change.
  2. An added file and a deleted file give ADDED and DELETED.
  3. A rename gives one RENAMED change with `old_path` set.
  4. Without `base_commit`, the base is the head's first parent.
  5. A root commit gives base `null` and every file ADDED.
  6. An unknown SHA gives COMMIT_NOT_FOUND.
  7. 301 or more changed files are all returned.
  8. A binary, an oversize file and a non-UTF-8 file land in `skipped[]`.
  9. The fixture repo is byte-identical before and after a run.
  10. `.gitignore`, `.github/x.md` and `src/a.py` give only `src/a.py`.
  11. A symlink is listed and skipped as `UNSUPPORTED_FILE_TYPE`, and a file-to-symlink switch is one TYPE_CHANGED change.
  12. A repo that doesn't exist gives REPOSITORY_NOT_FOUND.
- **More cases:**
  - Renames across hidden paths.
  - A base equal to the head.
  - An ambiguous or unfetchable short SHA.
  - Each validation error.
  - The 422 → 400 mapping.
  - Byte-identical `GET`.
  - Unknown `analysis_id`.
  - Three identical runs differ only in `analysis_id` and `created_at`.
  - No run saved and no clone left behind after an error.
  - TIMEOUT with a tiny configured deadline.
  - The category rules.
  - `config_version` changes when the rules file changes.
- **Network tests.** These are skipped when offline:
  - One request against a small public repo, for example `octocat/Hello-World` at `7fd1a60`.
  - The conformance test, which sends the same request set to the reference service and to ours and compares the results with `analysis_id`, `created_at` and `tool_version` removed (`tool_version` is a build label; Kaan, 2026-10-17), allowing only the DOCUMENTATION and `config_version` differences.
- **Prior art.** v0's tests use TestClient against the real app (`tests/test_receiver.py`), and `tests/conftest.py` puts `Source/` on the path and repoints config per test with `monkeypatch`. v1.1 tests follow the same pattern.
- **Regression.** The v0 suite keeps passing: 18 pass and 1 skips without a `.env`.

## Out of Scope

- The LLM drift check, findings in `issues[]`, the doc budget and `LLM_UNAVAILABLE`. These come in v1.2.
- The mapping file and its loader, which come in v1.3 if time allows, otherwise v2.
- The REST fallback, review, PR comments, a UI, section and symbol selectors, and tree-sitter.
- Hunks and line-level diffs.
- Copy detection.
- Durable run storage, which comes in v3.
- Merge-base handling for PRs, which belongs to the v3 Action.
- Wiring the webhook into `analyze()`, which comes in v4.

## Further Notes

- The reference service is the contract, so where the [connector guide](../../../plan/history/github-connector-steps.md) disagrees with it, the contract wins. That covers renames as one change, the code `REPOSITORY_NOT_FOUND`, and `TIMEOUT` as 500 with nothing saved.
- Tell the pod that their service returns OTHER for doc files and so fails T-04 as it stands.
- Still open: how lockfiles are classified (roadmap decision 17) and what the `/test` endpoints should do (confirm with the pod before that work starts).
- Free tier: runs vanish on spin-down and redeploy, so a `GET` after idle time can 404 on both teams' services.
