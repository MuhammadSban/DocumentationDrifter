# DocumentationDrifter website test suite

This runnable suite targets DocumentationDrifter's HTTP service and watch-list console in Chromium, including the v1.2 application. It starts both servers automatically when no URL is supplied, so Railway and GitHub are not needed for local runs. The bench-owned API replaces the LLM call with a deterministic no-findings test double; local and CI runs need no provider API key.

All new bench files are grouped here:

```text
testbench/
  run_testbench.py    One-command runner and HTML report generator
  local_app.py        Test-only API launcher with a no-findings LLM replacement
  requirements.txt   Bench dependencies and the existing app requirements
  pytest.ini         Bench test discovery
  tests/             API tests, browser tests and local-server fixtures
  DEMO.md            Presentation and submission walkthrough
  results/           Existing evidence and all future test run outputs
  reports/           Earlier test-results document and PDF
  archive/           Earlier review scripts, raw evidence and render previews
  ci/website.yml     GitHub Actions workflow template
```

Start with [DEMO.md](DEMO.md). From the repository root, run `python testbench/run_testbench.py --mode local`, then open the HTML report whose path is printed. Historical reports retain the exact commands and paths used before the files were moved; new runs record the new paths.

## Install

Use Python 3.12 or newer and Git, from the repository root:

```powershell
python -m pip install -r testbench/requirements.txt
python -m playwright install chromium --only-shell
```

Browser dependencies are separate from `requirements.txt`, so the deployed app does not include Playwright. The API tests need only the original requirements. Without Playwright, the browser module is explicitly skipped.

## Run locally

```powershell
python -m pytest testbench/tests -q -ra --junitxml=testbench/results/website.xml --screenshot=only-on-failure --tracing=retain-on-failure --output=testbench/results/browser
```

The suite builds the project's deterministic fixture repository, starts the actual Uvicorn API with isolated run and clone folders, and starts `Source/Frontend/ui.py` as its proxy. `testbench/local_app.py` replaces only `LLM_Shell.llm.check` inside that API subprocess, matching the original suite's approach without changing production code. Git comparisons, classification, HTTP handling and saved run retrieval remain real. It closes the server processes after the run. Your development server and normal run store are not used.

## Test Railway

The deployed service is at `https://documentationdrifter-production.up.railway.app`. Run the HTTP tests against it with:

```powershell
python -m pytest testbench/tests/test_api.py --website-url https://documentationdrifter-production.up.railway.app -q -ra --maxfail=1 --junitxml=testbench/results/railway.xml
```

Both the origin and a URL ending in `/system` are accepted. `DRIFTER_TARGET_URL` is an alternative to `--website-url`. An explicit option takes precedence. The suite waits up to 90 seconds for `/system/health` to become ready, then treats unavailable endpoints as failures.

Hosted analysis tests submit 15 labelled cases to the API using the published `kaan-kanadasi/DocumentationDrifter-testrepo` fixture. Successful analyses create run files; the session test also creates one unique course session. `DRIFTER_TEST_REPO=owner/name` can select another published copy with the same manifest and commit history. These tests do not depend on the other team's reference service or on local GitHub connectivity probes.

For a quick live check without cloning repositories or submitting analyses, use:

```powershell
python -m pytest testbench/tests/test_api.py --website-url https://documentationdrifter-production.up.railway.app -k "not fixture_analysis_and_saved_run" -q -ra
```

Each analysis request has a 180-second HTTP timeout. `--maxfail=1` stops the hosted comparison run after the first failure so an unavailable analysis service does not trigger 15 slow retries. A healthy `/system/health` response alone does not establish that analyses can finish.

Run browser tests against the locally served console backed by Railway with:

```powershell
python -m pytest testbench/tests --website-url https://documentationdrifter-production.up.railway.app -q -ra --maxfail=1
```

The v1.2 API also serves the console at `/`. Pass its page URL with `--console-url https://documentationdrifter-production.up.railway.app/` or `DRIFTER_CONSOLE_URL` to test that deployed page. If you separately host the console, it must proxy its `/system` requests to the API selected by `--website-url` for the real integration test to exercise the same service.

## What the suite checks

| File | Cases | Behavior |
|---|---:|---|
| `test_api.py` | 29 | Health, route discovery, OpenAPI with Team 16's six categories, input errors, malformed JSON, unknown runs, traversal-shaped IDs, 15 labelled comparisons, saved run bytes, course sessions and error shapes |
| `test_console.py` | 17 | Initial screen, form validation, duplicate watches, local storage, pause and remove controls, request payloads, changed and unchanged heads, rename and skip tables, counters, metadata, errors, expired runs and frontend regressions |

Most console cases mock GitHub and API responses to make specific states repeatable. One integration case mocks only GitHub's head lookup and sends the analysis through the real console proxy to the selected API, then checks the displayed result. Mocked cases do not establish live GitHub availability.

## Known frontend failures

Four browser cases assert desired behavior that the current console does not satisfy. They use `xfail(strict=True, raises=AssertionError)` so they remain visible without turning every normal run red. A fixed behavior causes an unexpected pass and fails the run until its marker is removed.

| Case | Current defect |
|---|---|
| `test_expired_run_can_be_recreated_without_a_new_commit` | Re-analyze does nothing when the stored head has not moved |
| `test_polling_recovers_after_github_rate_reset` | Polling never clears the exhausted request count after its reset time |
| `test_slow_previous_selection_does_not_replace_current_result` | An older response can replace the selected repository's result |
| `test_second_poll_does_not_duplicate_an_inflight_analysis` | A second poll can submit an identical analysis before the first completes |

To expose these as ordinary failing tests while working on fixes:

```powershell
python -m pytest testbench/tests/test_console.py --runxfail -q
```

Production application behavior is unchanged by this suite. Local runs return no findings through the LLM test double and do not evaluate model accuracy. Hosted runs use the deployed provider unchanged, require that deployment's provider credentials, and validate finding fields rather than assuming `issues[]` is empty. Provider failures remain test failures. Claude's use as a coding contributor does not configure the application's runtime model provider. The suite does not perform load testing or claim mobile layout or accessibility coverage.

## Results and CI

JUnit XML records each case's outcome. Playwright can retain screenshots and traces for failures using the local command above. Use `python -m playwright show-trace <trace.zip>` to inspect a trace. `testbench/results/` is gitignored.

The **Website tests** GitHub Actions workflow template is included at `testbench/ci/website.yml`. GitHub does not execute workflow files from that folder. To activate it later, copy it to `.github/workflows/website.yml`. When activated, it runs locally on pull requests, accepts hosted URLs on manual runs, and uploads JUnit XML and browser diagnostics. It does not deploy the site.

Browser setup and fixture usage follow the official [Playwright installation guide](https://playwright.dev/python/docs/intro) and [pytest plugin reference](https://playwright.dev/python/docs/test-runners).
