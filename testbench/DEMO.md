# DocumentationDrifter test bench demonstration

This is the demonstration guide for the test-bench deliverable. The bench supplies controlled inputs, sends them to the service or browser, checks assertions against expected behavior, and records individual results. It works without manually pasting fetch calls into Chrome.

## What the pending request screenshot proves

The HTTP 200 replies for `commits?per_page=1` establish that the browser retrieved a head commit from GitHub. The pending `analyze` requests establish only that requests were initiated. They do not establish that the service completed an analysis, returned the correct changes, or saved a retrievable run file. Those behaviors need assertions and completed responses.

The next step for the test-bench deliverable is to run the controlled local demonstration and present its generated evidence. Treat the live analysis stall as a separate deployment defect; it does not prevent demonstrating the bench against the local implementation.

## Deliverable files

| File | Role in the deliverable |
|---|---|
| `testbench/run_testbench.py` | Runs the bench and creates a readable HTML report, JUnit XML, console log and JSON summary |
| `testbench/local_app.py` | Launches the real local API with only the external LLM check replaced by a no-findings test double |
| `testbench/tests/test_api.py` | 29 HTTP cases, including 15 labelled repository comparisons and immediate retrieval of successful run files |
| `testbench/tests/test_console.py` | 17 browser cases for the console, including four known frontend defects |
| `testbench/tests/conftest.py` | Starts isolated local API and console processes, connects to hosted targets, and cleans up servers |
| `testbench/requirements.txt` | Installs the browser test dependencies alongside the original application requirements |
| `testbench/README.md` | Detailed test configuration and direct pytest commands |
| `testbench/DEMO.md` | The demonstration script and explanation of what each run establishes |
| `testbench/ci/website.yml` | CI template to copy into `.github/workflows/` when activating automated runs |
| The generated run folder under `testbench/results/bench/` | Execution evidence to show or submit alongside the source files |

Keep `testbench/` in the project repository. Its active suite reuses the existing `tools/testrepo.py`, `requirements.txt`, and the application in `Source/`. It supplies its own fixture setup and does not import the original test suite's `conftest.py`. Submit the project plus `testbench/` and a selected evidence folder, or deliver this folder to teammates who already have the project. Do not package `.venv`, credentials, or normal application run files. Historical review scripts under `archive/` also use the original `tests/` helpers.

## Preparation

From PowerShell in `C:\Users\barsh\Downloads\DocumentationDrifter`, use the project's virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r testbench/requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium --only-shell
```

Python 3.12 or newer and Git are required. The dependencies are already installed in the current workspace. These setup commands are for another machine or a fresh environment.

## Demonstration one local behavior

Run:

```powershell
.\.venv\Scripts\python.exe testbench/run_testbench.py --mode local
```

The bench creates the deterministic fixture repository, starts the real API and console, then runs HTTP and Chromium tests. The local API uses a no-findings LLM test double, so no Gemini, Claude or other provider API key is needed. This validates the application workflow with controlled model output, not model accuracy. You do not enter a repository or commit manually. The fixture manifest supplies exact head and base commits and expected lists of changes and skipped files.

At the end, the terminal prints the full path to `report.html`. Open that file in Chrome using Ctrl O, or double-click it in File Explorer. Every run gets its own timestamped evidence folder, so earlier runs are retained.

Use this presentation sequence:

1. Show the terminal command and explain that it starts the system under test automatically.
2. Open `test_api.py` at `test_fixture_analysis_and_saved_run`. Show that a manifest case supplies an input and the test compares the result's changes, commits and skipped files with expected values.
3. Show the final assertion comparing the saved GET response byte for byte with the POST response. This checks persistence as well as analysis output.
4. Open the HTML report. Show the run time, commit, mode, target and exact command.
5. Find the `renamed`, `docs-category` and `many-files` rows. Explain what those cases assert.
6. Filter the report to KNOWN FAILURE. Show the four reproduced frontend defects. They are explicitly separated from passed tests.
7. Open `test_browser_reaches_real_analysis_through_console_proxy` in `test_console.py`. This case drives the actual page and sends its analysis through the real console proxy to the API; only GitHub's head lookup is mocked.
8. Show the XML and console-log links as machine-readable and human-readable execution evidence.

The verified local result before this guide was 42 passed and four expected failures. The new run's actual report is the authority; do not claim those numbers if a later run differs. Most browser cases mock responses to reproduce specific states. Their passing results do not establish live GitHub or hosted-service availability.

## Demonstration two Railway basic API checks

Run:

```powershell
.\.venv\Scripts\python.exe testbench/run_testbench.py --mode smoke
```

This targets `https://documentationdrifter-production.up.railway.app` by default. It runs 14 HTTP checks for health, route discovery, schema, input validation, unknown runs and course-session behavior. It creates one unique course test session. It does not submit analyses or clone repositories. Use `--url https://another-host.example` to select another deployment.

Open the new HTML report and show its target and scope. A passing smoke result proves only those tested HTTP behaviors. It does not prove that an analysis can finish. This is why a healthy site can still have pending analysis requests in Chrome.

## Demonstration three Railway analysis completion

After checking the Railway analysis stall, run:

```powershell
.\.venv\Scripts\python.exe testbench/run_testbench.py --mode live
```

This runs all 29 API cases against Railway, including public fixture analyses. Hosted runs use the deployed LLM provider unchanged; its credentials must be configured on the deployment. The local LLM replacement never applies to hosted URLs. It uses the published fixture repository and verifies saved run retrieval after successful analyses. It stops after the first unexpected failure. Each analysis HTTP request has a 180-second timeout. A timeout or incorrect result must appear as a failure in the report; a stopped run is not evidence that the unexecuted cases passed.

If the deployed console and API share the address shown in Chrome, the browser suite can also target that actual page:

```powershell
.\.venv\Scripts\python.exe testbench/run_testbench.py --mode live --console-url https://documentationdrifter-production.up.railway.app/
```

This selects the full 46-case website suite. Most browser cases still use controlled responses; the integration case uses the real selected API. It does not claim that every browser request is unmocked.

## Showing known defects as failures

Normal runs mark four known console defects with `xfail(strict=True)`. The report calls them KNOWN FAILURE, not PASS. To demonstrate the failing assertions directly:

```powershell
.\.venv\Scripts\python.exe testbench/run_testbench.py --mode local --show-known-failures
```

This intentionally makes the known defects ordinary failures and returns a nonzero exit code. Use that report to explain what needs fixing. When a normally marked known failure is fixed, strict xfail causes an unexpected pass to fail the run until its marker is removed.

## Evidence to submit

For each run you present, retain its complete generated folder:

| Output | What it records |
|---|---|
| `report.html` | Searchable, filterable results with known defects separated from passes |
| `results.xml` | Per-case JUnit outcomes for CI and automated grading |
| `console.txt` | Complete pytest output, including failed assertions and setup errors |
| `summary.json` | Mode, target, commit, interpreter, exact command, exit code and per-case results |
| `browser/` when produced | Screenshots and traces retained for unexpected browser failures |

Reports record observed test execution. They are not application run files and do not replace the service's saved analysis results. No test-bench claim should rely only on a screenshot of pending requests.
