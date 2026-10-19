# 01: Wire the drift check into the analysis

**What to build:** `POST /system/analyze` fills `issues[]` from the LLM instead of returning it empty. Inside the `fetch()` block, the analysis gathers the changed code (every path not selected as documentation, minus anything already skipped, the base side read at `old_path` for a rename) and the documentation at head (selected independently of category by path, not an unsupported extension, not binary, decodes as UTF-8), fills a 200 KB budget in path order by raw bytes, and asks `LLM_Shell.llm.check()` once. Docs past the budget are omitted; the prompt is told how many were left out, without their paths. `skipped[]` retains Team 16's name-only rules and sole `UNSUPPORTED_FILE_TYPE` reason (TT-Q13). Every failure of that call, a spent deadline included, is 500 `LLM_UNAVAILABLE` with nothing saved. A yes/no verdict is read off `issues[]` being non-empty, not a new field.

**Blocked by:** None (v1.1 is done)

**Status:** ready-for-human · implemented on `kaan_test`, copied from `main` without merging. Deployment and the public fixture acceptance run remain. Historical live-model evidence is recorded below; it has not been repeated during this port.

**Spec:** docs/plan/roadmap.md, v1.2 (spec-v1.2.md not written yet)

- [x] `analyze()` calls `check()` once inside the clone's lifetime, and `issues[]` holds what it returns, sorted by `(documentation_file, code_file)`.
- [x] The code side carries both sides of every changed non-doc file; a rename reads its base side at `old_path`; a path already in `skipped[]` is left out.
- [x] The doc side carries every documentation path at head that is readable text, in path order, up to `DRIFTER_DOC_BUDGET_BYTES` (200 KB). `.pdf` joins the unsupported extensions.
- [x] A doc past the budget is counted only in the prompt, leaving `skipped[]` unchanged; an unchanged doc that is binary, unsupported or not UTF-8 is left out with no record.
- [x] `check()` is given the analysis deadline and spends what is left of it as the call's timeout; a deadline already gone raises `LLM_UNAVAILABLE` without calling out.
- [x] A failed call is 500 `LLM_UNAVAILABLE` and no run file is written.
- [x] An empty side makes no call at all, so a docs-only commit and a repo with no docs both cost nothing.
- [x] The console reads the verdict off `issues[]`. The response contains no budget skip entries.
- [x] Conformance keeps Team 16's six categories and name-only skip contract, with no budget skip entries to strip.
- [x] The suite is green offline without a key: the wiring tests stub `check()`, and `tests/conftest.py` stubs it for every other v1 analysis test.
- [x] One hand-run against the live model proves a real finding end to end through `POST /system/analyze` (`test_the_api_reports_drift_end_to_end`, marked `live_llm` so it opts out of the stub and skips without a key).
- [ ] AC-02 and AC-03 on the public test repo, with `planted_drift` filled (deliberately deferred, ticket 02).

## Comments

**2026-10-18.** Three defects in the shell showed up while wiring it, each fixed here: `genai.Client()` was built as a throwaway, so the SDK closed its transport before the request ("Cannot send a request, as the client has been closed"); `IssueType` and `LLM_UNAVAILABLE` were missing from `schemas.py`, so the module did not import; and `get_settings().llm_model` named a setting that did not exist. All three would have read as `LLM_UNAVAILABLE` at runtime, which is to say as a provider problem.

Reading the docs one file at a time cost 15.1 s per analysis of the test repo: in a blobless clone, `cat-file` fetches each missing blob on its own (314 doc files, ~47 ms each). Naming the files in one `git diff` first fetches them in a single request, as `git diff --numstat` already does for changed files, which brought the same analysis to 0.51 s. `Comparison.read_many()` owns that, and falls back to one read each where a batch dies whole, as it does on a submodule commit git cannot fetch.

**2026-10-18, port to `kaan_test`.** This ticket originally described `v1.2-llm-drift` and its earlier DOCUMENTATION/OVER_DOC_BUDGET design. TT-Q13 supersedes those public contract changes. The earlier author reported 200 offline passes, 56 skips and four live Gemini tests; the current port is validated separately without provider calls. Public AC-02/AC-03 remain deferred.
