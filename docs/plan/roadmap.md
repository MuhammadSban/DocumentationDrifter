# DocumentationDrifter roadmap: v0 → v4

Written 2026-10-16 against `main` @ `76eb691`. Revised the same day after probing the pod's live v1 service (`https://doc-tracker-5t4s.onrender.com/system`, tool_version 0.3.0). Other sources: the Phase 2 spec ([docs/vision/](../vision/README.md)), schema v14 ([pdf](../vision/documentation-tracker-schema-v14.pdf)), the M0 build order ([M0-build-order.pdf](history/M0-build-order.pdf)), the repo, and the earlier plans in this folder ([overall plan](history/documentation-drifter-plan.md), [fetcher plan](history/commit-fetcher-plan.md), [connector steps](history/github-connector-steps.md)). This file puts those plans in order as versions and doesn't repeat their detail. On 2026-10-17 it was revised again so that v1 pairs with a GitHub Action later without rework; the reasons are in [actions readiness](reports/actions-readiness.md).

**The product vision is inspiration, not a blueprint.** [docs/vision/](../vision/README.md) describes it. Each version (v1.1, v1.2, v2 and so on) takes ideas from it but is free to differ, so the team can build iteratively and change course as it learns. When a version departs from the product vision, the decision log or this roadmap says so; where they disagree, the roadmap and the decision log win.

**Working agreement.** Every version is built locally, one small slice at a time. Nothing is pushed or merged until Kaan says so for that push.

**Planning status (2026-10-17).** v1 planning is complete. Every v1 decision is either settled or has a default that stands unless Kaan changes it: Railway hosting (8, moved from Render on 2026-10-17), `.github/` excluded, confirmed by T12-Q9 (9), no DESIGN/ARCHITECTURE/SPECIFICATION/REQUIREMENT rules yet (11), lockfiles OTHER and skipped as `UNSUPPORTED_FILE_TYPE` (17, settled by T12-Q2). The Actions-readiness changes were applied on 2026-10-17 (decisions 14 and 15). The other open rows (5, 6, 7, 10) belong to v2 and v3 and get settled before those versions start. The `/test` semantics are to be confirmed with the pod before v1 slice 13.

---

## Goals

1. **Detect change.** Given a public repo, a head commit and an optional base, list every changed file with its category (REQ-01).
2. **Flag drift.** Point at documentation that is probably missing or outdated because the code it describes changed (REQ-02).
3. **Keep humans in charge.** Every finding is `PENDING_REVIEW`. The tool never edits the repo or its docs (REQ-03, REQ-06).
4. **Leave evidence.** Each run is saved as one JSON file that can be fetched back unchanged (REQ-04).
5. **Fail loudly and repeatably.** Bad input or an incomplete check returns an error, never a fake success. The same inputs give the same output (REQ-05, REQ-07).
6. **Stay simple.** An LLM decides drift from v1.2, probabilistic until the final version, which is deterministic (decision 4, overriding spec §8.2). Keep dependencies minimal (`AGENTS.md`).
7. **Match the pod's contract byte for byte.** The pod's live service is now the reference implementation. Both teams are tested against the same tester and the same repos (spec §5.3), so any difference from it counts as a bug unless the pod agrees to change it.

---

## What the pod's v1 service tells us

I read the service's OpenAPI and called it on 2026-10-16. Five analyses ran on public repos plus the error cases. Nothing was set up on the `/test` endpoints.

### The contract as built

| Item | What the live service does |
|---|---|
| Base path | Everything is under `/system`: `POST /system/analyze`, `GET /system/analysis/{id}`, `GET /system/health`. |
| Course endpoints | `POST /system/test/setup` (`session_id`, `setup`) and `GET /system/test/report?session_id=`. An unknown session returns 404 `{"message", "source":"system"}`. The OpenAPI calls these "course testing endpoints". |
| Request | `repository` ("owner/name"), `commit_id` (7–40 hex), `base_commit` (optional, defaults to the first parent). |
| `AnalysisResult` | All 12 fields are required: `analysis_id`, `repository`, `head_commit`, `base_commit`, `config_version`, `tool_version`, `status` (SUCCESS / ERROR), `error`, `issues`, `changes`, `skipped`, `created_at`. |
| `analysis_id` | `an-` followed by 32 hex characters (a uuid4 with no dashes). |
| `config_version` | Always a **string** (`"mapping-v1"`), never null. |
| `created_at` | ISO 8601 in UTC with milliseconds and a `Z` suffix. |
| `Change` | `path`, `old_path`, `change_type` (ADDED, MODIFIED, DELETED, RENAMED, COPIED, TYPE_CHANGED), `category`. |
| `category` enum | IMPLEMENTATION, DESIGN, ARCHITECTURE, SPECIFICATION, REQUIREMENT, OTHER. **There is no DOCUMENTATION value**, and `docs/user/quickstart.rst` came back as `OTHER`. |
| `Finding` | `finding_id`, `issue_type`, `code_file`, `documentation_file` (nullable), `change_category`, `explanation`, `verification_status`. The finding is **file-level** and has **no confidence field**. |
| `Skipped` | `path`, `reason`. |
| Errors | The body is `{"code", "message"}`. Missing `commit_id` gives 400 `INVALID_REQUEST` with "commit_id is required". A bad repo format gives 400 `INVALID_REQUEST`. A missing or private repo gives 404 **`REPOSITORY_NOT_FOUND`** ("not found or is not public"). An unknown SHA gives 404 `COMMIT_NOT_FOUND`. |
| Behaviour checked | A short SHA expands to the full 40 characters, and the base defaults to the first parent. `GET` returns the saved run byte-identical. Two identical runs differ only in `analysis_id` and `created_at`. `/health` reports `storage: "local"`. |

### What this changes in our design

1. **Our v1 is now a conformance job, not a design job.** The shapes and error codes are settled by a running service, so we build to its observed behaviour. We add a **conformance test** that sends the same requests to their URL and ours and compares the two results after stripping `analysis_id` and `created_at`.
2. **Docs are DOCUMENTATION (decided by Kaan, 2026-10-17).** The pod's live enum has no DOCUMENTATION value and returns `OTHER` for `docs/*.rst`, but M0's T-04 expects DOCUMENTATION, and that is the rule we follow. We add DOCUMENTATION to `Change.category` and `Finding.change_category`. The conformance test treats doc-file categories as a known difference until the pod's service adds the value, and the pod should be told that their service fails T-04 as it stands.
3. **Findings are file-level by contract.** `Finding` carries `code_file` and `documentation_file` only, with no heading path and no line spans. So v2 detection is file-level, which is also the spec's §9.1 fallback. Schema v14's section and symbol mapping moves to v4, because it would require extending the shared contract.
4. **Confidence is settled by omission.** The contract has no `confidence` field, so AC-10's "within 0.05" can't be tested as written. We propose dropping it from AC-10 rather than adding a field the other team doesn't emit.
5. **The `/system` prefix and the `/test` endpoints are part of what gets graded.** We mirror the prefix. We will build `/test/setup` and `/test/report` ourselves (decided by Kaan), but not in the first v1 slices. They come after the core API works (v1 slice 13).
6. **HTTP codes for failures are settled.** It's 400 or 404 with an `ErrorBody` when nothing is saved. That closes the old open question.
7. **The same hosting caveat applies to them.** Their Render service also stores runs on local disk. On the free tier that disk is wiped on every redeploy, restart and spin-down, and a service spins down after 15 idle minutes ([render.com/docs/free](https://render.com/docs/free)), so a run can 404 on `GET` after a quiet spell. Durable storage stays a v3 item for both teams.

Nothing here changes the version boundaries. It tightens what v1 must match, and it pushes finer-grained mapping out of v2.

---

## Where we are: v0 (done)

| Piece | State |
|---|---|
| Webhook receiver (`Source/GitHub_Connector/gitHook.py`) | FastAPI `POST /hooks/github`. It checks the HMAC, answers `ping`, dedupes on the delivery id and stores the push's `before`/`after` pair in SQLite. Also `GET /health`. |
| `parse.py`, `store.py`, `models.py`, `config.py` | Real code now, no longer stubs. |
| Tests | 19 pytest cases on the receiver and config. Re-run on 2026-10-17: 18 pass and 1 skips, because `test_dotenv_is_read_when_running_from_source` needs a `.env`, which is gitignored. |
| Not yet built | `/analyze`, `/analysis/{id}`, diffing, classification, run files, mapping, detection, review, deployment and CI. |

v0 was the receiver box of the webhook-connector outline, `WebHookConnectors.png`, removed from the repo and kept in git at `48e145e`, with delivery-id dedupe in SQLite; there is no queue, worker or reconciler. The tester calls the stateless `/analyze` API instead, so v1 builds that. v0 stays dormant in v1: the v1 app neither serves nor imports it. In v4 the webhook becomes one more caller of the same `analyze()` function (decision 14), so nothing in v0 is thrown away.

---

## v1: change detection API that matches the pod (spec Phase 3)

Every answer from the 2026-10-17 grilling, with its reason, is in the [decision log](decisions.md).

**Split (Kaan, 2026-10-17).** v1 ships in two steps. **v1.1** is the git change detection below (slices 1–13), with `issues[]` empty. **v1.2** adds an LLM that decides drift and fills `issues[]`. It is probabilistic on purpose for now; determinism comes back in the final version (decision 4).

Neither v1.1 nor v1.2 has a mapping file: the v1.2 LLM reads the changed files and the repo's doc files directly. The mapping file comes in **v1.3** if time allows, otherwise in v2 (Kaan, 2026-10-17).

The v1.2 LLM sits behind one function, with the provider and model set in config. v1.2 starts on Google Gemini's free tier (a Gemini Flash model, 1M context), with the API key stored as a Railway environment variable. Switching to Claude Haiku 5.5 or another provider later is a config change (Kaan, 2026-10-17; this replaces the earlier Claude API choice). The free tier's daily limits are Google's to change, and a rate-limited call fails the analysis.

When the LLM call fails (API down, timeout, rate limit or missing key), the whole analysis fails with 500 `LLM_UNAVAILABLE` and nothing is saved, so a missing check is never reported as SUCCESS (Kaan, 2026-10-17). `LLM_UNAVAILABLE` is a new error code beyond the pod's contract.

In v1.2, AC-10 and the conformance test still require `changes[]` to match exactly, but only check the shape of `issues[]`: each finding names a real changed file and a real doc file and has a valid issue type. The exact `issues[]` check returns when the final version is deterministic (Kaan, 2026-10-17).

`Finding` keeps the pod's shape with no confidence field; the LLM's reasoning goes in `explanation` (Kaan, 2026-10-17).

The LLM gets documentation at head selected independently of the six categories by the `documentation` and `not_documentation` lists in `path_rules.json`, up to a 200 KB total. Omitted docs are counted in the prompt; `skipped[]` remains name-based under TT-Q13.

**Settled by TT-Q13 and the `kaan_test` port.** The only public skip reason is `UNSUPPORTED_FILE_TYPE`; the doc budget adds no public skip entries.

**Goal.** For any input, our service gives the same answer as the pod's service, apart from `analysis_id` and `created_at`. In v1.1 `issues[]` is empty on purpose; v1.2 fills it from the LLM, and from then on only `changes[]` must match the pod exactly.

**How it's built.** The connector follows [GitHub connector, step by step](history/github-connector-steps.md) (the "guide") step for step: the git CLI through `subprocess`, the `fetch()` → `Comparison` interface from the [fetcher plan](history/commit-fetcher-plan.md), dataclasses inside the connector and Pydantic only for the API models. It lives in `Source/GitHub_Connector/` next to the v0 webhook code. Where the guide was written before the pod's service existed, the contract wins; the three places are listed under "Where the guide and the contract differ" below. Each slice is built locally and ends with green tests.

**Code layout.** v1 goes in new modules beside the v0 files, with names that don't reuse v0's `models`, `store`, `parse` or `config`: `api.py` (the app and routes), `analysis.py` (`analyze()`), `fetch.py` (the connector), `rules.py` plus its rules file, `runs.py` (the run store), `schemas.py` (the Pydantic models) and `settings.py` (the `DRIFTER_*` settings: limits, folders and the remote base URL, read with pydantic-settings as v0's `config.py` does). Imports stay `GitHub_Connector.*` with `Source/` on the path, as v0 does. v1 tests build their fixture repos in `tmp_path / "repo"`, because v0's autouse fixture writes `test.db` into `tmp_path`, and they use a fixture name other than `client`.

| # | Slice | Guide step | Done when |
|---|---|---|---|
| 1 | API skeleton under `/system`: `POST /analyze`, `GET /analysis/{id}` and `GET /health`, returning a hardcoded `AnalysisResult`. The Pydantic models copy the pod's OpenAPI field for field, plus DOCUMENTATION in the category enum. v1 is its own FastAPI app in `api.py`, with `openapi_url="/system/openapi.json"`, no lifespan and every route on `APIRouter(prefix="/system")`; it never imports `gitHook.app`. Handlers are plain `def` and only call `analyze()` in `analysis.py`, which raises `AnalysisError(code, message)`; the route maps the code to 400, 404 or 500. A `RequestValidationError` handler turns FastAPI's 422 into 400 `INVALID_REQUEST`. | — | Our `/system/openapi.json` schemas match theirs for `AnalysisRequest`, `AnalysisResult`, `Change`, `Finding`, `Skipped` and `ErrorBody`, apart from DOCUMENTATION. One test calls `analyze()` directly, without the HTTP client. |
| 2 | Validate the request before touching the network: `repository` matches `^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$`, `commit_id` is required and 7–40 hex, and `base_commit` follows the same rule when given. | 1 | Missing `commit_id` → 400 `INVALID_REQUEST` with "commit_id is required" (AC-07). `not-a-repo` → 400 `INVALID_REQUEST`, and no run is saved. |
| 3 | Connect anonymously: `GIT_TERMINAL_PROMPT=0` and `git -c credential.helper= clone --filter=blob:none --no-checkout --quiet` into a fresh temporary directory. Every git call has a 60 s timeout, and the whole analysis has a 120 s deadline; both map to `TIMEOUT`. At most K = 2 analyses run at once (a semaphore around `analyze()`), and extra requests wait. All three values live in config. The connector is used as `with fetch(repo, head, base) as cmp:`, and the clone is deleted when the block exits, so the v1.2 LLM step can read files inside the same scope. | 2 | A public repo clones. A missing or private repo fails at once → 404 `REPOSITORY_NOT_FOUND`, even in an environment that injects GitHub credentials. |
| 4 | Resolve the commits: `git fetch origin {sha}` when the head isn't in the clone, then `git rev-parse --verify {sha}^{commit}` for the full 40-hex id. The base is `base_commit` (resolved the same way) or `{head}^`. A root commit has base `null`, which is a first audit. Any `base_commit` is accepted and diffed exactly as given, even one equal to, after or unrelated to the head (decision 20). A short SHA that can't be fetched or is ambiguous gives 404 `COMMIT_NOT_FOUND` with a message asking for the full 40-character SHA (decision 21). | 3 | `octocat/Hello-World` at `7fd1a60` returns head `7fd1a60b…` and base `553c2077…`. An unknown SHA → 404 `COMMIT_NOT_FOUND` (AC-08). A root commit gives base `null`. |
| 5 | List the files at each commit with `git ls-tree -r {sha}` and keep only regular files (`100644`/`100755`) with no path segment starting with `.`. `.gitignore`, `.github/` and `.vscode/` drop out silently. Symlinks and submodules are left out of `tree(side)` but, outside hidden paths, a changed one is listed in `changes[]` and skipped as `UNSUPPORTED_FILE_TYPE` unread, except a switch to or from a regular file, which is one TYPE_CHANGED change that isn't skipped (T12-Q10, ticket 17). No `-l`: in a blobless clone it reads every blob's size and fetches missing blobs one at a time. Binary files (a NUL byte in the first 8 KB) and files over 1 MB go to `skipped[]` with a reason; these checks run only on changed paths, after `git diff --numstat` has fetched their blobs in one batch (it also marks binaries with `-`). This builds `tree(side)`. | 4 | A commit that adds `.gitignore`, `.github/x.md` and `src/a.py` lists only `src/a.py`. A symlink is not read, and a PNG lands in `skipped[]`. |
| 6 | Read file contents with `git show {sha}:{path}`, decoded as UTF-8. No cache in v1.1, since each changed file is read once; v1.2 adds one if the LLM step needs it. A path missing on one side returns `None`, and an undecodable file goes to `skipped[]`. This is `read(path, side)`. v1.1 uses it for the UTF-8 check, v1.2 uses it to read the docs and changed code it sends to the LLM, and v1.3 or v2 reads the mapping file with it. | 6 | `read(path, "base")` and `read(path, "head")` return the right bytes, and a missing side returns `None`. |
| 7 | Get the changes with `git diff --name-status -M {base} {head}`: renames only, at git's default 50% similarity, so COPIED never appears (decision 18). The step 5 filter applies, so `.gitignore` never appears in `changes[]`. A rename is **one** `RENAMED` change with `old_path` set (see below). The filter checks each side of a rename: a rename out of a hidden path is ADDED, a rename into one is DELETED, and a hidden path never appears as `old_path` (decision 19). A first audit diffs against the empty tree, so every file is `ADDED`. | 7 | T-01, T-02, T-03, T-06 and T-07 pass. More than 300 changed files all come back. |
| 8 | Classify each file, first matching rule wins: `requirements*.txt` → OTHER; `docs/**`, `*.md`, `*.rst`, `*.txt` → DOCUMENTATION; `src/**`, `tests/**`, `*.py`, `*.sh` → IMPLEMENTATION (`*.sh` from T12-Q11); everything else → OTHER. The rules live in one config file in our repo, and `config_version` is a short hash of that file, so it's always a string. | 5 | `docs/installation.rst` → DOCUMENTATION (T-04 passes). `psf/requests` at `d568f47` matches the pod's `changes[]` except that doc files are DOCUMENTATION here and `OTHER` there. |
| 9 | Hand it on and save: sort `changes[]` and `skipped[]` by path, write `runs/{analysis_id}.json` once, and have `GET` return it byte-identical. `analysis_id` is `an-<hex>`, and `created_at` has milliseconds and a `Z`. The temporary clone is deleted when the `fetch()` block exits. The run store is one module, `runs.py`, with `save(analysis_id, data)`, `load(analysis_id)` and the only serializer, `dump(result)`, so v3 swaps local disk for a durable store by changing that module. `runs/` goes into `.gitignore`. | 8 | Three identical runs differ only in `analysis_id` and `created_at` (AC-10). AC-06 and T-05 pass. No temporary clone is left behind, even after an error. |
| 10 | **Conformance test**: a pytest that sends the same requests (the cases above plus the error cases) to both URLs and compares the results. It is skipped when offline. | — | The only differences are the DOCUMENTATION category and `config_version`. |
| 11 | Minimal hosting: a Dockerfile with `git` installed, started with `uvicorn --app-dir Source GitHub_Connector.api:app`, and a Railway deploy (`railway.toml`). The README says the free service sleeps after about 5 to 10 minutes without outgoing traffic, its first request can take a moment or answer 502, and its disk is wiped on every redeploy and restart, so a `GET` for an old run can return 404. `GET /system/health` is the warm-up call. | — | The tester reaches our public URL. |
| 12 | CI: `.github/workflows/ci.yml` runs `python -m pytest -q` from the repo root on every PR, with `permissions: contents: read`. A second workflow, `acceptance.yml` (manual `workflow_dispatch`, optional schedule), warms the service through `/system/health` with retries, then runs T-01 to T-07 and the conformance test against the deployed URL. Spec §8.1 asks Actions to "run automated acceptance tests", and this job is the dry run for the v3 Action. | — | A PR shows a green check, and a manual run of `acceptance.yml` passes against the deployed URL. |
| 13 | Course endpoints `POST /system/test/setup` and `GET /system/test/report`, matching the pod's shapes. This comes after slices 1–12. | — | An unknown session gives 404 `{"message", "source":"system"}`. A session that was set up returns a report. The exact semantics are still to be confirmed with the pod. |

**Tests that come with the connector** (guide "Tests to write alongside", plus the nine fetcher-plan cases). They use tiny repos built with `git init` in `tmp_path` and need no network:

1. One modified line → one `MODIFIED` change.
2. An added file and a deleted file → `ADDED` and `DELETED`.
3. A rename → one `RENAMED` change with `old_path` set.
4. No `base_commit` → the base is the head's first parent.
5. A root commit → base `null` and every file `ADDED`.
6. An unknown SHA → `COMMIT_NOT_FOUND`.
7. 301 or more changed files → all of them are returned.
8. `read()` returns the right content on each side and `None` where the file is missing.
9. The fixture repo is byte-identical before and after a run (AC-09).
10. `.gitignore`, `.github/x.md` and `src/a.py` added → only `src/a.py` appears in `tree()` and `changes[]`.
11. A symlink and a binary PNG → neither is read, and the PNG is in `skipped[]`.
12. A private repo cloned without credentials → `REPOSITORY_NOT_FOUND`.

The guide's merge-base test (a PR whose base branch moved on) belongs to the v3 GitHub Action, because a direct API call diffs exactly the `base_commit` it is given. One optional network test runs against a small public repo and is skipped when offline.

### Where the guide and the contract differ

The guide predates the pod's live service. In these three places v1 follows the contract, because the shared tester checks it, and the guide carries a note saying so.

| Topic | Guide says | Contract / v1 does | Why |
|---|---|---|---|
| Renames (guide step 7) | Emit a rename as two changes, DELETED then ADDED. | One `RENAMED` change with `old_path` set. | M0 says the same ("not a delete + add"), the live enum has `RENAMED`, and T-03 checks it. |
| Missing or private repo (step 2, error table) | `REPO_NOT_FOUND` / `REPO_NOT_ACCESSIBLE` | `REPOSITORY_NOT_FOUND`, HTTP 404. | That is the code the pod's service returns. |
| `TIMEOUT` HTTP code (error table) | 500, or 200 + ERROR, pending the pod. | 500 with an `ErrorBody` and nothing saved, the same as other failures before a run file exists. | The pod's service answers failures with `{code, message}` and no saved run. |

**Deliberately left out of v1:** the REST fallback (our Docker image ships git, so it isn't needed yet), the mapping loader (v1.3 if time allows, otherwise v2), review, PR comments, a UI beyond the basic console, section and symbol selectors, and tree-sitter.

**A basic UI is in v1 (Kaan, 2026-10-18; [decision log](decisions.md), ticket 18).** The v1 app serves the console in `Source/Frontend/` at `/`, outside the `/system` contract, and `ui.py` still runs it against an API elsewhere. It calls only `POST /system/analyze` and `GET /system/analysis/{id}`, so it works against v1.1 unchanged and shows v1.2's `issues[]` once they are filled. Anything richer, such as run history, stays in v2.

**Acceptance criteria for v1**

- AC-01, AC-07, AC-08 and AC-10 (without the confidence clause) pass automatically against our test repo (spec §6.1). AC-06 and AC-09 also pass.
- All twelve connector tests above pass.
- The conformance test shows no differences from the pod's service apart from the DOCUMENTATION category, `config_version`, `tool_version` (T12-Q5) and the named known differences in the decision log.
- The shared tester's T-01 to T-07 pass.
- The existing v0 tests still pass (18 pass; the `.env` test skips without a `.env`).
- No code from the analysed repo is installed, imported or run, and no file from it is written to disk except as git objects in the temporary clone.
- A public **test repo** with labelled cases exists (spec §4.2). v2's reliability run reuses it.

**Acceptance criteria added by v1.2**

- AC-02 and AC-03 are exercised on the test repo, with the LLM deciding the findings.
- AC-10 and the conformance test still match `changes[]` exactly; `issues[]` passes the shape check (each finding names a real changed file and a real doc file and has a valid issue type).
- Docs past the 200 KB budget are omitted and counted in the prompt without adding entries to `skipped[]`.
- A failed LLM call (down, timeout, rate limit or missing key) returns 500 `LLM_UNAVAILABLE` and saves nothing.

---

## v2: mapping and reliability (spec Phase 4)

**Goal.** Findings already come from the v1.2 LLM. v2 adds the authored mapping (unless v1.3 shipped it), so the LLM judges known doc–code pairs instead of the whole doc set, and measures reliability.

*Updated 2026-10-17:* items 2 and 3 below were written for a hand-written rule. Since decision 4 they describe what the LLM is asked to judge for each mapped pair, not code we write.

**Scope**

1. **Mapping file loader.** Read an authored mapping at base and at head. It uses the pod's `mapping.json` if they publish one; otherwise it's `doctracker.yml`, which must not be a dot-file. A bad file → `INVALID_CONFIG`. `config_version` stays a short hash, now over the rules file plus the mapping file at head (M3). It is always a string, like the pod's `mapping-v1`, and the conformance test treats it as a known difference.
2. **File-level rule.** Each link maps a doc file to code files or folders.
   - Code changed and doc not → `OUTDATED_DOCUMENTATION`.
   - Link kept but the doc deleted → `MISSING_DOCUMENTATION`.
   - Both changed → no finding.
   - Each finding fills `code_file`, `documentation_file`, `change_category` and a templated `explanation`, and has `verification_status: PENDING_REVIEW`.
3. **Docs detection.** The documentation path selector from v1.2 decides which side of a link is documentation; reported categories retain Team 16's six values.
4. **Reliability run** on the test repo (spec §9.1). The target is ≥90% of planted drift caught and <10% false alerts.
5. **Conformance** with the pod's v2 once they ship it: the same mapping and the same commit should give the same `issues[]`.
6. **GitHub Action** in the analysed repo, replacing the console's polling as the way a push reaches the service (decision 14), moved here from v3 on 2026-10-18. A push took about 4½ minutes through the console's 300 s poll, and polling faster runs into GitHub's anonymous limit of 60 calls an hour. The measurements, a diagram and the downsides are in the [v2 README](../Models/v2/README.md). It is a thin client of `POST /system/analyze` and needs no checkout. A sketch is in [actions readiness](reports/actions-readiness.md). How a run it starts reaches the console is still open; see [poll or SSE](../Models/v2/poll_or_sse.md).
   - **Base and head** follow [guide step 3](history/github-connector-steps.md), and the Action always sends a real base. The merge bases come from `merge_base_commit` in GitHub's compare endpoint. On a PR, head is `pull_request.head.sha` and base is the merge base of `pull_request.base.sha` and head. On a push, head is `after` and base is the merge base of `before` and `after`, which is `before` unless the push was forced. A new branch (`before` all zeros) uses the merge base with the default branch (decision 15, explained with graphs in the [decision log](decisions.md#decision-15-the-base-for-a-push-that-creates-a-branch-2026-10-17)). With pushes filtered to the default branch, that happens only when the default branch is first created; the merge base then equals the head, so the Action skips that push. A deleted branch is skipped. The guide's merge-base test lands here.
   - **Triggers and permissions.** `push` on the default branch plus `pull_request`, never `pull_request_target`. `contents: read`, with `pull-requests: write` only in a separate comment job for same-repo PRs, because fork PRs get a read-only token.
   - **Calls.** `GET /system/health` with retries first, to ride out the cold start, then one `POST` with a long timeout and no retry.
   - **Results.** The summary goes to `$GITHUB_STEP_SUMMARY`, which works on fork PRs, and the run file is uploaded as an artifact. Artifacts expire within 90 days, so that is a copy, not the REQ-04 evidence. Until v3's durable storage, a push to this repo's `main` also redeploys Railway and wipes the run store, so there the artifact is the only copy.
   - **Distribution.** Our repo is public (checked 2026-10-18), so other repos can `uses:` a reusable workflow from it.

**Acceptance criteria for v2**

- AC-02: when code changed and docs didn't, the correct doc file is flagged with the code file named.
- AC-03: when code and docs changed together, there is no warning.
- AC-10: repeated runs give the same files and issue types.
- Reliability on the test repo meets the §9.1 target.
- All v1 criteria still pass.

---

## v3: hosted review loop (spec Phase 5)

**Goal.** Anyone can run an analysis on a public repo, see findings on their PR, review them, and find the saved result later.

**Scope**

1. **Durable run storage.** Railway's container disk is wiped on every redeploy and restart. Its Free plan allows one 0.5 GB volume, which could hold run files; otherwise the free durable option is an evidence repo written through the Contents API. Either sits behind the `runs.py` interface from slice 9.
2. ~~**GitHub Action**~~ Moved to v2 item 6 (Kaan, 2026-10-18; why: the [v2 README](../Models/v2/README.md)).
3. **Review recording.** `POST /system/analysis/{id}/review` (or PR-comment replies read back) stores the decision, the reviewer and a timestamp alongside the run. The run file itself is never rewritten. Agree on the shape with the pod first, because it extends the shared contract.
4. ~~**Connect v0's webhook** to `analyze()`~~ Moved to v4 (decision 14). The Action covers push and PR events, and on the free tier a webhook sent while the service sleeps is lost.
5. **Run history**: list past runs for a repo, shown in the v1 console (served at `/` since ticket 18) if the course still requires the Phase 3 "documentation viewer". The pod's service has no UI.
6. **Safety hardening**: anonymous access, timeouts and the 1 MB file cap already ship in v1. v3 adds a cap on the number of changed files and on repo size.

**Acceptance criteria for v3**

- AC-04: a run with a finding shows it as `PENDING_REVIEW`, and the repo is untouched.
- AC-05: an authorised reviewer confirms or dismisses a finding, and the decision, reviewer and timestamp are saved.
- AC-06: each run is a separate JSON file with the repo, commit, status and findings, and it survives a redeploy.
- AC-09: the analysed repo is byte-identical before and after a run.
- AC-10 still holds on the hosted service.
- The spec §6.3 demo works: public repo → analysis → finding → review → saved result in the history.

---

## v4 and later (only by conscious choice)

Each of these stays out until Kaan decides to add it (per `AGENTS.md`):

- Section- and symbol-level mapping from schema v14 (`heading_path`, `path::name` selectors, hunk overlap, 1-hop dependencies). This needs the pod to extend `Finding`.
- A GitHub App with per-user sign-in and repo "sleep/revive" (the original outline in `store.py` at `5b74560` and the webhook-connector outline, `WebHookConnectors.png`, removed from the repo and kept in git at `48e145e`).
- Wiring v0's webhook to `analyze()` (decision 14). It needs an always-on host, because GitHub gives a webhook 10 seconds and doesn't redeliver failures on its own, and a job table or background worker, because an analysis takes longer than the ack. The receiver first gets its own router, since including `gitHook.app` would also bring its lifespan and root routes.
- Running the analysis inside the consumer's runner (a CLI over `analyze()` against the runner's checkout), for scale-out and private repos. Those runs never reach our service, so they can't be reviewed or listed there.
- Notifications. The spec names these as the first thing to cut.
- A richer viewer UI.
- More languages through tree-sitter adapters.
- Following renames, and comparing facts (signatures against docs) instead of checking whether code and docs changed together (spec review note 1).
- Private repos with a token.
- The REST fallback from guide steps 2–6, for hosts without git.
- Making the LLM drift check deterministic for the final version (decision 4), so AC-10 again holds for `issues[]` exactly.

---

## Decisions needed (they change what gets built)

| # | Question | Recommended | Blocks |
|---|---|---|---|
| 1 | ~~Docs category~~ | **Decided:** DOCUMENTATION (Kaan, 2026-10-17). Tell the pod that their service returns `OTHER`. | — |
| 2 | ~~Who builds `/test`~~ | **Decided:** we build it, after the core v1 slices (slice 13). | — |
| 3 | ~~Diff source~~ | **Decided:** the git CLI (Kaan, 2026-10-17). It has no 300-file cap and no rate limit, and matches spec §8.1. Steps are in the [connector steps](history/github-connector-steps.md). | — |
| 4 | ~~LLM at runtime~~ | **Decided:** an LLM decides drift, starting in v1.2, and is probabilistic for now (Kaan, 2026-10-17). v1.1 is git change detection only. The final version is deterministic. This overrides the product vision's §7, §8.2 and §9.1, which kept AI out of the running system. | v1.2 |
| 5 | ~~Confidence~~ | **Decided:** no confidence field; `Finding` keeps the pod's shape and the LLM's reasoning goes in `explanation`. AC-10 is checked without its confidence clause (Kaan, 2026-10-17). | — |
| 6 | Mapping file name and format (also guide open point 2), and whether the pod's `mapping-v1` refers to one. | Use whatever the pod uses. Otherwise `doctracker.yml`, which isn't hidden, so the filter doesn't drop it. Needed only once the mapping lands, in v1.3 or v2 (decision of 2026-10-17). | v1.3 or v2 |
| 7 | Where reviews live: a review endpoint or PR replies. | A small review endpoint agreed with the pod. It's testable for AC-05. | v3 |
| 8 | ~~Host~~ | **Decided:** Railway (Kaan, 2026-10-17), replacing Render, whose free tier needs a card on file that wouldn't verify. Railway's Free plan needs no card: 0.5 GB RAM per service after a 30-day, $5 trial, with sleep-when-idle turned on so the monthly usage allowance lasts. In v3, durable runs go to its 0.5 GB volume or to an evidence repo. | v1 slice 11, v3 |
| 9 | ~~Exclude `.github/` docs such as `CONTRIBUTING.md`?~~ (guide open point 1) | **Decided:** yes, as every hidden path is ignored (T12-Q9, Kaan, 2026-10-17), even though the reference service lists them; a known difference by choice. | v1 slice 5 |
| 10 | Diff PRs from the merge base rather than `pull_request.base.sha`? (guide open point 3) | Yes, in the Action (v2 since 2026-10-18), which reads it from the compare endpoint. Agree it with the pod. | v2 |
| 11 | Path rules for DESIGN, ARCHITECTURE, SPECIFICATION and REQUIREMENT (guide open point 4) | None in v1. Until the pod agrees on conventions such as `docs/design/**`, those files count as DOCUMENTATION under `docs/` or when named `*.md`, `*.rst` or `*.txt`, and as OTHER otherwise. | v1 slice 8 |
| 12 | ~~`requirements.txt` caught by `*.txt`~~ | **Decided:** `requirements*.txt` → OTHER, ahead of the `*.txt` rule (Kaan, 2026-10-17). | — |
| 13 | ~~Save failed analyses?~~ | **Decided:** no (Kaan, 2026-10-17). A failure returns 400, 404 or 500 with an `ErrorBody` and saves nothing, which matches the pod's service and models M2 and M4. Phase 2's M2 drew saved ERROR runs with HTTP 200; v1 does not do that. | — |
| 14 | ~~Which v3 trigger: the Action, the webhook, or both?~~ | **Decided:** the Action only, and wiring the webhook moves to v4 (Kaan, 2026-10-17, applying [actions readiness](reports/actions-readiness.md)). Both on `push` would analyse every push twice, and on the free tier the webhook loses deliveries sent while the service sleeps. The Action moved from v3 to v2 (Kaan, 2026-10-18; why: the [v2 README](../Models/v2/README.md)). | — |
| 15 | ~~What base does a new-branch push send?~~ | **Decided:** the merge base with the default branch (Kaan, 2026-10-17). The contract can't ask for a first audit for a head that isn't a root commit, and a first audit would list the whole repo as ADDED. "First audit" (base `null`) now means a root commit only. Graphs and reasoning: the [decision log](decisions.md#decision-15-the-base-for-a-push-that-creates-a-branch-2026-10-17). | — |
| 16 | ~~Keep hunks in v1?~~ | **Decided:** dropped from v1.1, with no `git diff -U0` and no `unidiff` (Kaan, 2026-10-17). v1.2 may still pass the plain `git diff` text to the LLM. | — |
| 17 | ~~Lockfiles~~ | **Decided** by T12-Q2 (Kaan, 2026-10-17): a lockfile is OTHER in `changes[]` and also skipped as `UNSUPPORTED_FILE_TYPE`, as the reference service does. | — |
| 18 | ~~Detect copies?~~ | **Decided:** renames only, `-M` at git's default 50% similarity, so COPIED never appears (Kaan, 2026-10-17). The conformance test shows whether the pod differs. | — |
| 19 | ~~Rename across the hidden-path filter?~~ | **Decided:** filter each side separately (Kaan, 2026-10-17, confirmed by T12-Q9). `.github/a.md` → `docs/a.md` is ADDED, and `docs/x.md` → `.archive/x.md` is DELETED. A hidden path never appears, `old_path` included. | — |
| 20 | ~~Odd base commits?~~ | **Decided:** accept any `base_commit` and diff exactly what was given (Kaan, 2026-10-17). A base equal to the head gives an empty `changes[]` and SUCCESS; a base after the head or from unrelated history gives whatever `git diff base head` says. | — |
| 21 | ~~Short SHAs outside branches?~~ | **Decided:** a short SHA that can't be fetched (not on any branch or tag) or is ambiguous gives 404 `COMMIT_NOT_FOUND`, with a message asking for the full 40-character SHA (Kaan, 2026-10-17). | — |
| 22 | ~~Deadline and K?~~ | **Decided:** 120 s overall deadline, 60 s per git call, K = 2 analyses at once, all in config (Kaan, 2026-10-17). | — |

Settled by the pod's service: HTTP codes for failures (400/404 with `{code, message}`), the error code names, rename as one change, `config_version` as a string, and `analysis_id` format.
