# DocumentationDrifter specification

**The one current spec: what the service does and what counts as correct behaviour.** Updated 2026-10-18. v1.1 (change detection) is built and deployed; v1.2 (an LLM that fills `issues[]`) is next and is marked *planned* wherever it appears. How each version was built, and why, stays in its own files: [spec-v1.1.md](Models/v1/v1.1/spec-v1.1.md), the [roadmap](plan/roadmap.md) and the [decision log](plan/decisions.md). Where this page and the code disagree, the code on `main` is what is deployed; fix this page.

Words are defined in [CONTEXT.md](../CONTEXT.md). The rules behind each part are drawn as models M1 to M5 in [Models/v1/](Models/v1/README.md).

## 1. What the service is for

Given a public GitHub repository and two commits, the service lists every file that changed and what kind of file it is, and (from v1.2) flags documentation the change may have made outdated. It supports people who keep technical documentation current; it never decides for them.

Three rules hold in every version:

- **Read-only.** The analysed repository is never changed, and none of its code is run (REQ-06).
- **People decide.** Every finding is `PENDING_REVIEW`; the service never approves or edits documentation (REQ-03).
- **Fail loudly.** Bad input or an incomplete check returns an error, never a fake success (REQ-05).

## 2. Interface

Deployed at `https://documentationdrifter-production.up.railway.app`. Every contract route is under `/system`, and the OpenAPI document is `/system/openapi.json`. No authentication.

| Route | Purpose |
|---|---|
| `POST /system/analyze` | Run one analysis and return the saved run. |
| `GET /system/analysis/{analysis_id}` | Return a saved run byte for byte. |
| `GET /system/health` | Warm-up check: `{"status": "ok", "storage": "local"}`. Does no git work. |
| `POST /system/test/setup`, `GET /system/test/report` | Course test routes (section 4). |
| `GET /system` | Lists the routes. Not in the OpenAPI document. |
| `/tester/test/…` | The cross-team tester (section 5), with its own OpenAPI document. |
| `GET /` | The web console. Not part of the contract. |

**Request** (`AnalysisRequest`): `repository` ("owner/name", required), `commit_id` (7 to 40 hex characters, required), `base_commit` (same format, optional).

**Result** (`AnalysisResult`, all twelve fields always present):

| Field | Meaning |
|---|---|
| `analysis_id` | `an-` followed by 32 hex characters. |
| `repository` | As requested. |
| `head_commit` | The full 40-character SHA. |
| `base_commit` | The full SHA, or `null` for a root commit (a first audit). |
| `config_version` | A short hash of the path rules file. Always a string. |
| `tool_version` | `1.1.0+<short deploy commit>`. |
| `status` | `SUCCESS` for every saved run. |
| `error` | `null` on a saved run. |
| `issues` | `Finding[]`. Empty in v1.1; filled by the LLM in v1.2 (*planned*). |
| `changes` | `Change[]`, sorted by path: `path`, `old_path` (set only for RENAMED), `change_type`, `category`. |
| `skipped` | `Skipped[]`, sorted by path: `path`, `reason` (a code). |
| `created_at` | ISO 8601 UTC with milliseconds and a `Z`. |

`Finding` has `finding_id`, `issue_type` (MISSING_DOCUMENTATION or OUTDATED_DOCUMENTATION), `code_file`, `documentation_file`, `change_category`, `explanation` and `verification_status` (always `PENDING_REVIEW`). It has no confidence field.

**Errors.** A failed request saves nothing and returns `{"code", "message"}`:

| Code | HTTP | When |
|---|---|---|
| `INVALID_REQUEST` | 400 | A missing or malformed field, or a body that isn't a JSON object. Checked before any network call. |
| `REPOSITORY_NOT_FOUND` | 404 | The repository doesn't exist or isn't public. |
| `COMMIT_NOT_FOUND` | 404 | The head or base can't be found, or a short SHA is ambiguous or not on any branch or tag. |
| `TIMEOUT` | 500 | A git call took over 60 s or the analysis over 120 s. |
| `WRITE_FAILED` | 500 | The run file couldn't be saved. |
| `LLM_UNAVAILABLE` | 500 | *Planned for v1.2:* the LLM call failed, so the check is incomplete. |

An unknown or malformed `analysis_id` on `GET` returns 404 `{"code": "ANALYSIS_NOT_FOUND", "message": "analysis <id> does not exist"}`.

## 3. Behaviour

- **Commits.** The head is resolved to its full SHA. The base is `base_commit` when given, otherwise the head's first parent, otherwise `null` for a root commit, in which case every file is ADDED. Any given base is diffed exactly as given.
- **Changes.** `git diff --name-status -M` between base and head. A rename is one RENAMED change with `old_path` set; copies are never reported, so COPIED never appears. A switch between a file and a symlink is one TYPE_CHANGED change.
- **Hidden paths.** Paths with a segment starting with `.` (`.github/`, `.gitignore`, …) are reported in `changes[]`, with the same category and skipped-file rules as any other path. A rename into or out of a hidden path remains one RENAMED change with `old_path` set.
- **Categories.** The same answers as Team 16's system for any path (TT-Q12, TT-Q13). The first matching rule in [path_rules.json](../Source/GitHub_Connector/path_rules.json) wins, matched from the repository root, case-sensitive, where `**/` also matches no folder and `*` stays within one segment: REQUIREMENT for `requirements/**`, `docs/requirements/**`, `**/REQUIREMENTS*.md`; SPECIFICATION for `spec/**`, `specs/**`, `docs/spec/**`, `docs/specs/**`, `**/openapi*.yaml`, `**/openapi*.yml`, `**/openapi*.json`; ARCHITECTURE for `docs/architecture/**`, `**/ARCHITECTURE*.md`, `**/model_config.*`; DESIGN for `docs/design/**`, `docs/adr/**`, `**/DESIGN*.md`; IMPLEMENTATION for `.py`, `.ipynb`, `.js`, `.ts`, `.java`, `.c`, `.h`, `.cpp`, `.hpp`, `.go`, `.rs`, `.rb`, `.sh` and `.sql` files in any folder; anything else, doc files included, OTHER.
- **Skipped files.** A changed file is skipped by its name alone, as Team 16's system does (TT-Q13): it stays in `changes[]` and is also listed in `skipped[]` as `UNSUPPORTED_FILE_TYPE`, unless its extension (any case) is one of `.py`, `.ipynb`, `.js`, `.ts`, `.java`, `.c`, `.h`, `.cpp`, `.hpp`, `.go`, `.rs`, `.rb`, `.sh`, `.sql`, `.md`, `.rst`, `.txt`, `.yaml`, `.yml`, `.json`, `.toml`, `.cfg`, `.ini`, `.csv`, or its exact name is `LICENSE`, `Makefile`, `Dockerfile`, `README` or `CODEOWNERS`. No file is read to decide, and symlinks and submodules follow the same rule. The lists are in `path_rules.json`.
- **Saving.** Each successful run is written once as `runs/{analysis_id}.json`, and `POST` and `GET` return the same bytes. Runs live on the container's disk and are lost on redeploy or restart.
- **Repeatability.** The same repository, commits and rules give the same result, apart from `analysis_id` and `created_at` (REQ-07). From v1.2 this holds for `changes[]` only, because the LLM is probabilistic.
- **Limits.** At most 2 analyses run at once; extra requests wait. Public repositories only, cloned anonymously.

## 4. Course test routes (the automated test runner)

These run on the deployed app; their base URL is `https://documentationdrifter-production.up.railway.app/system/test`. `POST /system/test/setup` takes `{"session_id", "setup"}` (`session_id` 1 to 200 characters, `setup` any object) and answers 201 `{"session_id"}`, or 409 if the id is taken. `GET /system/test/report?session_id=…` reports how many executable lines of the v1 code ran since that setup: `{"session_id", "coverage": {"code": {"covered", "total", "basis"}}}`. Errors on these routes are `{"message", "source": "system"}`; an unknown session is 404. Sessions live in memory, so a redeploy forgets them.

## 5. Tester (cross-team testing)

The tester runs the shared test list against any team's system over HTTP and returns a suite report. It is served by the same app at `https://documentationdrifter-production.up.railway.app/tester`; plain `/tester` lists its routes and `/tester/openapi.json` is its OpenAPI document, separate from `/system`'s. It reaches a target only through `target_url`, the system's base URL ending in `/system`, so it tests our own system like any other.

| Route | Purpose |
|---|---|
| `POST /tester/test/setup` | `{"target_url"}`. Makes a new UUID, calls the target's `POST {target_url}/test/setup` with `{"session_id", "setup": {}}`, and answers 201 `{"session_id"}` once the target answered 201. A failed target setup is passed back with its status, message and source (a source outside the four below becomes `unknown`), and its id can't be run; a target answering anything else below 400 gives 500 `unknown`. |
| `POST /tester/test/run` | `{"session_id"}`. Warms the target once with `GET {target_url}/health`, runs every shared test once, reads `GET {target_url}/test/report?session_id=`, stores the suite report and returns it. Each target call is limited to 90 s (`TESTER_CALL_TIMEOUT`) and the suite to 600 s (`TESTER_SUITE_TIMEOUT`); a call that times out alone is `error`/`communication`. Past the suite limit, or when the tester itself fails, the test in flight becomes `error`/`tester`, the untried ones `skip`, `coverage.code` is null, the report is stored and the run answers 500 `{"message", "source": "tester"}`. A session runs once: a second run, during or after the first, is 409 and leaves the report unchanged. |
| `GET /tester/test/report?session_id=` | The stored suite report, unchanged, without running anything. 409 until the suite ends. |

**Suite report:** `{"session_id", "target_url", "results", "coverage"}`. Each result is `{"test_id", "outcome", "message", "source"?}`, `outcome` one of `pass`, `fail`, `error`, `skip`, and `source` present on an `error` only. `coverage.code` is copied from the target's report; `coverage.component` and `coverage.system` are `{"covered", "total", "basis"}`. A count the tester can't give is `null`, never zero, with `basis` saying why.

**Component and system coverage** (decision TT-Q3, TT-Q7 row 8). Each shared test is tagged, where it is defined, with the components and acceptance criteria it exercises. A component or criterion is covered once at least one executed test (any outcome but `skip`) carries it, and `basis` lists the covered IDs in Team 16's wording. System coverage counts AC-01 to AC-10 (section 6). The components are the pod's seven parts:

| ID | Component | Phase | A test exercises it when it |
|---|---|---|---|
| C1 | Web-service interface | 3 | sends a request to a contract route and judges the answer |
| C2 | Repository fetch | 3 | names a repository or commit the system must find, real or missing |
| C3 | Change detection and classification | 3 | relies on the changes the system computes |
| C4 | Mapping detector | 4 | checks `issues[]`; no shared test does yet |
| C5 | Result building and persistence | 3 | needs a successful, saved result |
| C6 | Saved-result retrieval | 3 | reads a run back with `GET /analysis/{id}` |
| C7 | Review workflow | 5 | records a reviewer's decision; no shared test does yet |

| Tests | Components | Criteria |
|---|---|---|
| T-01 to T-07 | C1, C2, C3, C5 | AC-01 |
| T-08 to T-11 | C1 | AC-07 |
| T-12, T-13 | C1, C2 | AC-08 |
| T-14 | C1, C6 | AC-06 |
| T-15 | C1, C6 | AC-06, AC-08 |
| T-16 | C1, C2, C3, C5, C6 | AC-06 |
| T-17 | C1, C2, C3, C5 | AC-10 |

These are Team 16's tags. With T-01 to T-17 executed they give component 5/7 (C1, C2, C3, C5, C6) and system 5/10 (AC-01, AC-06, AC-07, AC-08, AC-10), the numbers Team 16's tester reports on their own system, with the same `basis` sentences. AC-06 is counted although Phase 2 §6.1 lists only AC-01, AC-07, AC-08 and AC-10 for Phase 3, because Team 16's suite counts it.

**Copied from Team 16's suite** (decision TT-Q12). Team 16 agrees only to what their own tester checks, so every request, expected answer and pass rule below is copied from it: `doctracker/tester/suite.py` and `commits.json` in `ParthGupta06/doc-tracker` at `0db21ca`, read on 2026-10-18. Where this differs from Phase 2 or from our earlier tickets, their suite wins.

**Judging.** An error test passes on the expected HTTP status and error `code` with a non-empty `message`, never on the message's wording. Any 5xx where the test expects something else is `error` with source `system`, and no answer is `error` with source `communication`. A test that analyses needs 200, a result that passes Team 16's check (`analysis_id`, `repository`, `head_commit`, `config_version`, `tool_version` and `status` strings, `issues`, `changes` and `skipped` lists, `status` SUCCESS or ERROR, each change with string `path`, `change_type` and `category`, each finding `PENDING_REVIEW`), and `status` SUCCESS. Each message states what was expected and what came back. Each target call has a 90 s limit.

**The shared test list so far,** run in this order, against the pod's fixture repo `ParthGupta06/doc-tracker-fixtures` (decision TT-Q8). `Source/Tester/expected_changes.json` holds the fixture commits by tag, the same SHAs as Team 16's `commits.json`, and T-01 to T-07's expected answers, so it can be handed to Team 16 as it is. T-18 to T-23 are always `skip`, with Team 16's titles, tags and reasons (ticket 05): T-18 to T-20 wait for the Phase 4 detector, T-21 for its findings, T-22 for the Phase 5 review workflow and T-23 for Phase 5's code inspection.

| Test | Request | Pass when |
|---|---|---|
| T-01 | `c1-impl-only` | `base_commit` is its first parent `c0-initial`, and `src/model.py` MODIFIED IMPLEMENTATION |
| T-02 | `c2-add-mod-del` | `docs/model.md` MODIFIED OTHER, `src/eval.py` ADDED and `src/train.py` DELETED, both IMPLEMENTATION |
| T-03 | `c3-rename` | `src/evaluate.py` RENAMED from `src/eval.py`, IMPLEMENTATION |
| T-04 | `c4-categories` | four files MODIFIED as ARCHITECTURE, DESIGN, REQUIREMENT and SPECIFICATION |
| T-05 | `c6-binary` | `assets/logo.png` MODIFIED and `data/weights.bin` ADDED, both OTHER, and both in `skipped[]` as `UNSUPPORTED_FILE_TYPE` |
| T-06 | `c3-rename` with `base_commit` `c0-initial` | `base_commit` returned as sent, and `docs/model.md` MODIFIED OTHER, `src/evaluate.py` ADDED, `src/model.py` MODIFIED and `src/train.py` DELETED, all three IMPLEMENTATION |
| T-07 | `c0-initial`, a root commit | `base_commit` null and 11 changes, all ADDED; categories aren't checked |
| T-08 | `POST /analyze` without `commit_id` | 400 `INVALID_REQUEST` |
| T-09 | the body `{"repository": "x/y", "commit_id": ` | 400 `INVALID_REQUEST` |
| T-10 | `repository` `"not a repo"` | 400 `INVALID_REQUEST` |
| T-11 | `commit_id` `12345678`, a number | 400 `INVALID_REQUEST` |
| T-12 | `pod15-16-nonexistent/does-not-exist-7f3a` | 404 `REPOSITORY_NOT_FOUND` |
| T-13 | `commit_id` of forty zeros | 404 `COMMIT_NOT_FOUND` |
| T-14 | analyse `c1-impl-only`, then `GET /analysis/{id}` | the GET body equals the POST body |
| T-15 | `GET /analysis/an-` followed by 32 zeros | 404 `ANALYSIS_NOT_FOUND` |
| T-16 | analyse `c2-add-mod-del` twice | two different ids, both read back unchanged |
| T-17 | analyse `c4-categories` five times | the runs agree on `repository`, `head_commit`, `base_commit`, `status`, `changes` and `skipped`, and on `issues` apart from `finding_id`; `tool_version`, `config_version` and `created_at` aren't compared |

T-01 to T-06 compare `changes[]` as an unordered set of (path, old_path, change_type, category), and each message names the expected and received sets. Doc files are OTHER because Team 16's contract has no DOCUMENTATION. Our own system passes all seven since tickets 06 and 07.

**Errors** are `{"message", "source"}`: 400 for a missing or malformed body or query, or a `target_url` with a query or fragment (source `tester`), 404 for an unknown session or route, 405 for a wrong method, 409 for a report asked for before the suite ends or a second run of a session, 500 for a suite aborted past its limit or by a tester failure (source `tester`), 500 for an unreachable target (source `communication`). Source is one of `tester`, `system`, `communication` or `unknown`. Sessions and reports live in memory, so a redeploy forgets them.

## 6. What counts as correct

**Acceptance criteria** (Phase 2 spec section 4):

| Criterion | Checks | Status |
|---|---|---|
| AC-01 | Every changed file is found and labelled correctly. | Passes (v1.1) |
| AC-02, AC-03 | Outdated docs are flagged; docs updated with the code are not. | v1.2 (*planned*) |
| AC-04, AC-05 | Findings wait for review; a reviewer's decision is recorded. | v3 |
| AC-06 | Each run is a separate retrievable JSON file. | Passes until a redeploy; durable storage is v3 |
| AC-07, AC-08 | Missing input and unknown commits return errors, not success. | Passes (v1.1) |
| AC-09 | The analysed repository is unchanged. | Passes (v1.1) |
| AC-10 | Repeated runs give the same result (without the confidence clause, since there is no confidence field). | Passes for `changes[]` |

**Labelled test repo.** T-01 to T-07 and the other labelled cases run against [DocumentationDrifter-testrepo](https://github.com/kaan-kanadasi/DocumentationDrifter-testrepo) (built by `tools/testrepo.py`).

**How we run the tests.** The course tester drives the app through the routes in section 4. Our own [Acceptance workflow](https://github.com/MuhammadSban/DocumentationDrifter/actions/workflows/acceptance.yml) warms the deployed service, runs the labelled cases against it, then compares it with the reference service. [CI](../.github/workflows/ci.yml) runs the full pytest suite on every pull request.

**Conformance with the reference service.** The other team's service (`https://doc-tracker-5t4s.onrender.com/system`) is the reference: any difference is a bug unless it is one of these known differences, each recorded in the decision log:

- `config_version` and `tool_version` differ by design.
- The wording of the unknown-commit message, and of a test setup with no body.

## 7. v1.2 additions (planned)

- An LLM (a Gemini Flash model on Google's free tier, set in config) reads the changed files and the repository's documentation files at head (which files count is open, since DOCUMENTATION is no longer a category, TT-Q12) and fills `issues[]`. Each finding names a real changed file and a real doc file, has a valid `issue_type`, and is `PENDING_REVIEW`; the reasoning goes in `explanation`.
- Doc files past a 200 KB total budget go to `skipped[]` with a doc-budget reason.
- Any failed LLM call (down, timeout, rate limit, missing key) fails the whole analysis with 500 `LLM_UNAVAILABLE`, and nothing is saved.
- Conformance still matches `changes[]` exactly; `issues[]` is checked only for shape.
- The free key limits the whole service to 5 requests a minute, 250K tokens a minute and 20 requests a day.

## 8. Known limitations

Listed in the [README](../README.md#the-system-as-delivered-phase-3-updated-2026-10-18): runs and test sessions lost on redeploy, the size and time caps, public repositories only, no review loop, and the console's 300 s GitHub poll.
