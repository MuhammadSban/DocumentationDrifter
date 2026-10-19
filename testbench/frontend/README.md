# Test bench dashboard

This is a separate frontend for the DocumentationDrifter test bench. It runs the existing suite through a local Python server and reads actual reports from `testbench/results/bench/`. It has no Node.js build step or additional dependencies beyond the test bench requirements.

From the project root:

```powershell
.\.venv\Scripts\python.exe testbench/serve_testbench.py
```

Open **http://127.0.0.1:8765**. Keep the terminal running; Ctrl+C closes the dashboard and any run it owns. Use `--port 8766` if the default port is occupied.

On a fresh machine, install the dependencies and browser first:

```powershell
python -m pip install -r testbench/requirements.txt
python -m playwright install chromium --only-shell
```

## Using the dashboard

1. Select **Local suite** to start an isolated API and console and run all 46 website cases. Controlled LLM output makes this mode independent of API keys.
2. Click **Run local suite**. The execution panel streams actual output; only one run is allowed at a time. Cancel stops the owned process tree and marks the job cancelled, never passed.
3. When the run ends, inspect the result counts. Passed, unexpected failures, known defects and skipped cases remain separate.
4. Filter or search the test table and click a test name to inspect its recorded assertion evidence.
5. Open the full HTML report or download XML, JSON or the console log. Run history loads completed evidence folders and survives dashboard restarts.

**Smoke check** runs 14 basic HTTP checks against the configured deployment and creates one course test session. **Live analysis** submits 15 fixture analyses as part of 29 API cases; supplying a deployed console URL includes the browser suite for 46 cases. Hosted modes use the deployment's real model configuration and credentials. They do not replace the deployed LLM call.

**Show known defects as failures** uses the runner's existing `--show-known-failures` option. It intentionally makes reproduced frontend bugs fail the run. Normal Local runs currently have four expected failures; those are not counted as passes. Local runs test application workflow with controlled model output, not model accuracy.

The dashboard binds to `127.0.0.1` and uses this checkout's Python environment and files. Historical results describe the source version recorded when each run executed. An interrupted run without a summary does not appear as completed evidence. Full dashboard job logs are stored under `testbench/results/dashboard/`.

## Files and checks

- `testbench/serve_testbench.py`: local API, runner process ownership and artifact serving.
- `testbench/frontend/index.html`, `styles.css`, `app.js`: responsive dashboard.
- `testbench/ui_tests/test_dashboard.py`: tests for run options, output, evidence access, concurrent runs and cancellation.
- `testbench/ui_tests/test_dashboard_browser.py`: runs the actual Local suite through Chromium, checks filtering and downloads, and captures desktop and mobile previews.

Run the dashboard's own checks with:

```powershell
.\.venv\Scripts\python.exe -m pytest testbench/ui_tests -q --output=testbench/results/dashboard-browser
```
