# DocumentationDrifter
A program to detect documentation drift in a GitHub repo. Designed for ECE30861 Class Project.

v1.1 is built: given a public repo and two commits, it lists every changed file with its change type and category. v1.2 is implemented on `kaan_test`: an LLM flags documentation that contradicts the changed code.

**Start here:** [docs/README.md](docs/README.md) is the map of the documentation, with the order to read it in. The words used are defined in [CONTEXT.md](CONTEXT.md), the house rules are in [AGENTS.md](AGENTS.md), and the open review items are in [.scratch/v1-1-change-detection/to_do.md](.scratch/v1-1-change-detection/to_do.md).

## The system as delivered (Phase 3, updated 2026-10-18)

**Deployed web service:** <https://documentationdrifter-production.up.railway.app>. The console is at `/` and the API under `/system`; plain `/system` lists the routes and `/system/openapi.json` is the contract. Both the backend and the web console run as one Python 3.12 Docker container on Railway's free plan in the US East (Ohio) region, and Railway builds the branch selected in its service settings. Deploying `kaan_test` requires selecting that source branch; a merge into `main` is not required.

**Tester:** implemented on `kaan_test` at `/tester`, beside `/system`. The current public deployment still returns 404 for `/tester`; verify it after deploying this branch. Point it at any team's system with `POST /tester/test/setup {"target_url"}`, then `POST /tester/test/run {"session_id"}` returns the suite report, and `GET /tester/test/report?session_id=…` returns it again. Its routes are in [docs/spec.md](docs/spec.md), section 5.

**Tester run notes** (for the registry): *Setup:* `POST /tester/test/setup` calls the system's `POST {target_url}/test/setup` with `{"session_id", "setup": {}}` and waits up to 90 s for its 201. *Run:* `POST /tester/test/run` warms the system once with `GET {target_url}/health`, then runs T-01 to T-23 in order (T-18 to T-23 are skipped until Phases 4 and 5), each project call limited to 90 s and the whole suite to 600 s. A session runs once; a second run is 409. Past 600 s the run answers 500 and `GET /tester/test/report` has the results so far. *System setup:* nothing is prepared or reset, and sessions may run at the same time. The limits are set by `TESTER_CALL_TIMEOUT` and `TESTER_SUITE_TIMEOUT`, in seconds.

**Automated test runner:** the course test routes on the same app, base URL <https://documentationdrifter-production.up.railway.app/system/test>. `POST …/setup` opens a test session and `GET …/report?session_id=…` reports which lines of the v1 code the tester's requests ran. We also run the [Acceptance workflow](https://github.com/MuhammadSban/DocumentationDrifter/actions/workflows/acceptance.yml) against the deployed app (T-01 to T-07 on the labelled [test repo](https://github.com/kaan-kanadasi/DocumentationDrifter-testrepo), then conformance with the reference service), and [CI](.github/workflows/ci.yml) runs the whole pytest suite on every pull request.

**Interfaces**

| Route | What it does |
|---|---|
| `GET /` | The web console: watch repos, start analyses, open saved runs. |
| `POST /system/analyze` | Analyses `{"repository", "commit_id", "base_commit"?}` and returns the saved run. |
| `GET /system/analysis/{analysis_id}` | Returns a saved run byte for byte; an unknown id is 404 `ANALYSIS_NOT_FOUND`. |
| `GET /system/health` | Warm-up check, does no git work. |
| `POST /system/test/setup`, `GET /system/test/report` | Course test routes: open a session, then report the lines of v1 code that ran since. |
| `POST /tester/test/setup`, `POST /tester/test/run`, `GET /tester/test/report` | The cross-team tester: run the shared tests against any team's system. |

**Functionality.** For a public GitHub repo and two commits, the service lists every changed file with its change type (ADDED, MODIFIED, DELETED, RENAMED, TYPE_CHANGED) and category from ordered path rules that give the same answers as Team 16's system (REQUIREMENT, SPECIFICATION, ARCHITECTURE, DESIGN, IMPLEMENTATION or OTHER), lists files it couldn't check in `skipped[]` with a reason code, and saves each run as one JSON file. Failures before a result is built return 400, 404 or 500 with `{code, message}` and save nothing. Above 2000 changed files, the service saves an HTTP 200 `ERROR` result with `CHANGE_LIMIT_EXCEEDED`. v1.2 fills `issues[]` with documentation drift findings; model failures return 500 `LLM_UNAVAILABLE` and save nothing.

**Specification:** [docs/spec.md](docs/spec.md) is the one current spec: the interface, the behaviour rules, what counts as correct, and what v1.2 adds. The models behind it are M1 to M5 in [docs/Models/v1/](docs/Models/v1/README.md), and the next step (the GitHub Action, v2) is in [docs/Models/v2/](docs/Models/v2/README.md).

**Known limitations**

- **Runs don't survive a redeploy.** The service is always on for now, but it's still a work in progress, and any redeploy or restart wipes saved runs and test sessions, so an older analysis ID can return 404.
- **Gemini limits.** Drift detection uses a free Gemini API key as a temporary "oracle", which limits the whole service to 5 requests per minute, 250K tokens per minute and 20 requests per day, so podmates and graders should keep test runs few and spaced out.
- **Size and time caps.** At most 2 analyses run at once (others wait), and each is capped at 120 seconds.
- **Public repositories only**, read anonymously.
- **No review loop yet.** Findings can't be confirmed or dismissed; that is planned for v3.
- **The console finds new commits by polling GitHub every 300 s**, within GitHub's anonymous limit of 60 calls an hour, so a push can take up to 5 minutes to show. v2 replaces this with a GitHub Action.

## v1.1 change detection API

`POST /system/analyze` takes `{"repository": "owner/name", "commit_id": "<7-40 hex>", "base_commit": "<optional>"}` and returns every changed file of a public GitHub repo with its change type and category. `GET /system/analysis/{analysis_id}` returns the saved run byte for byte. The contract matches the reference service; see `docs/Models/v1/v1.1/spec-v1.1.md`.

**Dot-paths.** Files such as `.github/workflows/ci.yaml` and `.gitignore` are reported like any other path, with the same category and skip rules. A rename into or out of a dot-path stays one RENAMED change with `old_path` set.

**Route list.** Opening plain `/system` returns the list of routes. The reference service has no such route; it stays out of the OpenAPI document.

**Course test routes.** `POST /system/test/setup` with `{"session_id": "...", "setup": {...}}` opens a session (201, or 409 if the id is taken). `GET /system/test/report?session_id=...` then reports how many executable lines of the v1 code ran while handling requests since that setup: `{"session_id", "coverage": {"code": {"covered", "total", "basis"}}}`. Both match the reference service's shapes and error bodies (`{"message", "source": "system"}`). Sessions live in memory, so a restart or redeploy forgets them and their report becomes 404.

**Test repo.** The labelled test cases live in a public repo, [kaan-kanadasi/DocumentationDrifter-testrepo](https://github.com/kaan-kanadasi/DocumentationDrifter-testrepo), built by `tools/testrepo.py`. The online label tests use it by default (`DRIFTER_TEST_REPO=owner/name` points them elsewhere, an empty value turns them off). After changing any label, republish it from an account that can push there: `python tools/testrepo.py /tmp/testrepo` then `git -C /tmp/testrepo push --force https://github.com/kaan-kanadasi/DocumentationDrifter-testrepo main`. The `label/*` tags are optional; the tests find labels by the SHAs in the manifest. `DRIFTER_LABEL_CONFORMANCE=1` also compares every label with the reference service; it stays off until the ticket 12 differences are settled.

**Run locally**

```bash
pip install -r requirements.txt
uvicorn --app-dir Source GitHub_Connector.api:app --port 8000
python -m pytest -q            # DRIFTER_OFFLINE=1 skips the GitHub tests
```

**Container:** `docker build -t drifter .` then `docker run -p 8000:8000 drifter`. The image has git, no credentials, and serves only the v1 app.

**Drift check:** set `GEMINI_API_KEY` in the environment; without it an analysis that needs the model returns `LLM_UNAVAILABLE`. `DRIFTER_LLM_MODEL` selects the Gemini model and `DRIFTER_DOC_BUDGET_BYTES` caps documentation input (204800 bytes).

**Settings** (environment, all optional): `DRIFTER_REMOTE_BASE_URL`, `DRIFTER_RUNS_DIR`, `DRIFTER_CLONE_DIR`, `DRIFTER_RULES_FILE`, `DRIFTER_GIT_TIMEOUT` (60 s), `DRIFTER_ANALYSIS_DEADLINE` (120 s), `DRIFTER_MAX_CONCURRENT` (2), `DRIFTER_MAX_CHANGED_FILES` (2000).
