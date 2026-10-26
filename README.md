# DocumentationDrifter
A program to detect documentation drift in a GitHub repo. Designed for ECE30861 Class Project. 

v1.1 and v1.2 are built and deployed. Given a public repo and two commits, v1.1 lists every changed file with its change type and category. v1.2 then asks Google Gemini which documentation the changed code contradicts, and returns each finding in `issues[]` marked `PENDING_REVIEW`; its findings can vary between runs and their accuracy has not been measured.

**Start here:** [docs/README.md](docs/README.md) is the map of the documentation, with the order to read it in. The words used are defined in [CONTEXT.md](CONTEXT.md), the house rules are in [AGENTS.md](AGENTS.md), and the open review items are in [.scratch/v1-1-change-detection/to_do.md](.scratch/v1-1-change-detection/to_do.md).

## v1 API

`POST /system/analyze` takes `{"repository": "owner/name", "commit_id": "<7-40 hex>", "base_commit": "<optional>"}` and returns every changed file of a public GitHub repo with its change type and category, plus the drift findings in `issues[]`. `GET /system/analysis/{analysis_id}` returns the saved run byte for byte. The contract is the pod's API description (OpenAPI 0.3.0); see `docs/Models/v1/v1.1/spec-v1.1.md` for change detection and the "Wiring the LLM drift check" section of [the decision log](docs/plan/decisions.md) for the drift check.

**Errors.** Every failure answers with `{"code", "message"}`: 400 `INVALID_REQUEST`, 404 `REPOSITORY_NOT_FOUND` or `COMMIT_NOT_FOUND`, and 500 `TIMEOUT`, `WRITE_FAILED`, `LLM_UNAVAILABLE` (the drift check failed) or `INTERNAL_ERROR` (anything unforeseen). The last two are ours, not yet in the pod's contract. A failed request saves nothing.

**API docs.** `/system/docs` is an interactive Swagger UI page for every route; the machine-readable description is `/system/openapi.json`.

**Route list.** Opening plain `/system` returns the list of routes. The reference service has no such route; it stays out of the OpenAPI document.

**Course test routes.** `POST /system/test/setup` with `{"session_id": "...", "setup": {...}}` opens a session (201, or 409 if the id is taken). `GET /system/test/report?session_id=...` then reports how many executable lines of the v1 code ran while handling requests since that setup: `{"session_id", "coverage": {"code": {"covered", "total", "basis"}}}`. Both match the reference service's shapes and error bodies (`{"message", "source": "system"}`). Sessions live in memory, so a restart or redeploy forgets them and their report becomes 404.

**Cross-team tester.** The tester the course grades lives at `/tester` (Swagger at `/tester/docs`). `POST /tester/test/setup` with `{"target_url": "https://<host>/system"}` opens a session on that system and returns `{"session_id"}`; `POST /tester/test/run` with `{"session_id"}` runs the shared tests T-01 to T-23 (T-18 to T-23 skipped until later phases) and returns the report with results and code, component and system coverage; `GET /tester/test/report?session_id=...` returns the stored report. Errors are `{"message", "source"}`. A run makes about 15 analyses of Team 16's fixture repo, most of which reach the drift check, so it needs Gemini quota. Against our own system T-02, T-04, T-05 and T-06 fail on purpose: our categories and skip reasons differ from Team 16's.

**Test repo.** The labelled test cases live in a public repo, [kaan-kanadasi/DocumentationDrifter-testrepo](https://github.com/kaan-kanadasi/DocumentationDrifter-testrepo), built by `tools/testrepo.py`. The online label tests use it by default (`DRIFTER_TEST_REPO=owner/name` points them elsewhere, an empty value turns them off). After changing any label, republish it from an account that can push there: `python tools/testrepo.py /tmp/testrepo` then `git -C /tmp/testrepo push --force https://github.com/kaan-kanadasi/DocumentationDrifter-testrepo main`. The `label/*` tags are optional; the tests find labels by the SHAs in the manifest. `DRIFTER_LABEL_CONFORMANCE=1` also compares every label with the reference service; it stays off until the ticket 12 differences are settled.

**Run locally**

```bash
pip install -r requirements.txt
uvicorn --app-dir Source GitHub_Connector.api:app --port 8000
python -m pytest -q            # DRIFTER_OFFLINE=1 skips the GitHub tests
```

**Container:** `docker build -t drifter .` then `docker run -p 8000:8000 drifter`. The image has git, no credentials, and serves only the v1 app.

**Settings** (environment): `GEMINI_API_KEY` is required for any analysis that reaches the drift check; without it those fail with `LLM_UNAVAILABLE`. Optional: `DRIFTER_REMOTE_BASE_URL`, `DRIFTER_RUNS_DIR`, `DRIFTER_CLONE_DIR`, `DRIFTER_RULES_FILE`, `DRIFTER_GIT_TIMEOUT` (60 s), `DRIFTER_ANALYSIS_DEADLINE` (120 s), `DRIFTER_MAX_CONCURRENT` (2), `DRIFTER_MAX_FILE_BYTES` (1 MB), `DRIFTER_DOC_BUDGET_BYTES` (200 KB), `DRIFTER_LLM_MODEL`.

**Public URL:** https://documentationdrifter-production.up.railway.app/system, on Railway's free plan (`railway.toml`: Dockerfile build, `/system/health` health check). Every push to `main` redeploys it. The service is always on; `GET /system/health` is still the quickest way to check it is up.

## Known limitations

- **Saved runs are temporary.** Run files live on local disk, which is wiped on every restart and redeploy, so a `GET` for an old run can return 404. Fetch a run right after creating it and keep your own copy. Durable storage is a later version.
- **About 20 AI-checked analyses a day for everyone.** The drift check runs on Gemini's free tier (5 requests a minute, 20 a day). Past that, analyses that need it fail with 500 `LLM_UNAVAILABLE` until midnight Pacific time. A change with no code, or a repo with no docs, makes no call.
- **Findings are unmeasured suggestions.** They can differ between runs, only contradicted documentation is reported (not missing documentation), and there is no way yet to confirm or dismiss one.
- **Your code and docs go to Google.** The changed files and the documentation are sent to Gemini's free tier, where Google may use them. Only analyse repos you are happy to share.
- **Waiting has no limit.** At most 2 analyses run at once, and a request waiting for a slot has no time limit, so if analyses get stuck, later requests hang. Set a client timeout and check `GET /system/health`. Each analysis is stopped 120 s after it starts.
- **Not everything is checked.** Only the first 200 KB of documentation is sent (the rest is `OVER_DOC_BUDGET` in `skipped[]`); files over 1 MB, binary or non-UTF-8 files are skipped; hidden paths are ignored; only public repos work.
