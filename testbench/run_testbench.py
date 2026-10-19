# runs the website bench and turns its actual pytest evidence into a readable HTML report

from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
RAILWAY = "https://documentationdrifter-production.up.railway.app"


def read_cases(path: Path) -> list[dict]:
    # keeps known failures distinct from passed tests and ordinary skipped coverage
    if not path.is_file():
        return []
    cases = []
    for node in ET.parse(path).iter("testcase"):
        status, detail = "PASS", "All assertions in this test completed."
        for tag, outcome in (("error", "ERROR"), ("failure", "FAIL"), ("skipped", "SKIP")):
            issue = node.find(tag)
            if issue is not None:
                status = "KNOWN FAILURE" if issue.get("type") == "pytest.xfail" else outcome
                detail = issue.get("message", "") + ("\n" + issue.text if issue.text else "")
                break
        cases.append({
            "module": node.get("classname", ""), "name": node.get("name", ""),
            "status": status, "seconds": node.get("time", "0"), "detail": detail.strip(),
        })
    return cases


def write_report(folder: Path, metadata: dict, cases: list[dict], console: str) -> None:
    # escapes test output so filenames and error messages remain text in the report
    esc = html.escape
    counts = Counter(case["status"] for case in cases)
    if not cases:
        verdict = "No test case evidence was produced"
    elif metadata["exit_code"]:
        verdict = "Run failed or stopped early"
    elif counts["KNOWN FAILURE"]:
        verdict = "Completed with known defects"
    elif counts["SKIP"]:
        verdict = "Completed with skipped coverage"
    else:
        verdict = "Completed without reported failures"
    descriptions = {
        "local": "Local API and console with a no-findings LLM test double; no provider key is required and model accuracy is not evaluated. GitHub replies are mocked in browser cases; one case exercises the real browser to proxy to API path with the GitHub lookup mocked.",
        "smoke": "Live HTTP checks for health, routes, schema, validation, unknown runs and course sessions. This mode does not submit analyses and does not prove that analyses complete.",
        "live": "Live fixture analyses and immediate retrieval of saved runs, plus API checks. Stops after the first unexpected failure. A supplied console URL also enables browser checks against that page.",
    }
    badges = "".join(f'<div class="metric"><strong>{counts[label]}</strong><span>{label}</span></div>' for label in ("PASS", "FAIL", "ERROR", "KNOWN FAILURE", "SKIP"))
    rows = []
    for index, case in enumerate(cases, 1):
        status = case["status"]
        rows.append(
            f'<tr data-status="{esc(status)}"><td>TB{index:03d}</td>'
            f'<td class="status {status.lower().replace(" ", "-")}">{esc(status)}</td>'
            f'<td><small>{esc(case["module"])}</small><div>{esc(case["name"])}</div>'
            f'<details><summary>Result evidence</summary><pre>{esc(case["detail"])}</pre></details></td>'
            f'<td>{esc(case["seconds"])} s</td></tr>'
        )
    if not rows:
        rows.append('<tr><td colspan="4">No JUnit test cases were available. Inspect the console log below.</td></tr>')
    options = "".join(f'<option>{label}</option>' for label in ("ALL", "PASS", "FAIL", "ERROR", "KNOWN FAILURE", "SKIP"))
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DocumentationDrifter test bench results</title>
<style>
*{{box-sizing:border-box}} body{{margin:0;background:#f4f6f8;color:#172536;font:15px/1.5 system-ui,sans-serif}}
main{{max-width:1160px;margin:auto;padding:32px 24px}} h1{{font-size:30px;margin:0 0 8px}} h2{{font-size:20px}}
.meta,small{{color:#526375}} .verdict{{font-weight:700;font-size:19px}} .metrics{{display:flex;flex-wrap:wrap;gap:12px;margin:24px 0}}
.metric{{background:white;border:1px solid #d6dfe7;border-radius:8px;min-width:145px;padding:14px}}
.metric strong{{display:block;font-size:28px}} .metric span{{font-size:12px;font-weight:700}}
.controls{{display:flex;gap:12px;margin:16px 0}} input,select{{font:inherit;padding:8px;border:1px solid #aebdcb;border-radius:4px}}
input{{flex:1;min-width:0}} .tablewrap{{overflow-x:auto}} table{{width:100%;border-collapse:collapse;background:white}}
th,td{{padding:12px;text-align:left;border:1px solid #d6dfe7;vertical-align:top}} th{{background:#24384b;color:white}}
td:nth-child(1),td:nth-child(2),td:nth-child(4){{white-space:nowrap}} td:nth-child(3){{overflow-wrap:anywhere}}
.pass{{color:#166534}} .fail,.error{{color:#b42318}} .known-failure,.skip{{color:#8a4b00}} .status{{font-weight:700;font-size:12px}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef2f6;padding:12px;font-size:12px}} summary{{cursor:pointer}}
a{{color:#0758a5}} code{{overflow-wrap:anywhere}} .note{{max-width:900px}}
@media print{{body{{background:white}}main{{padding:0}}.controls{{display:none}}thead{{display:table-header-group}}tr{{break-inside:avoid}}}}
</style></head><body><main>
<h1>DocumentationDrifter test bench results</h1>
<p class="meta">{esc(metadata['started_at'])} | Mode {esc(metadata['mode'])} | {metadata['elapsed_seconds']:.2f} seconds</p>
<p class="verdict">{esc(verdict)}</p><p><b>Target</b> {esc(metadata['target'])}</p>
<p class="note">{esc(descriptions[metadata['mode']])}</p>
<p class="note">Known failures are defects reproduced by tests, not successful behavior. Skipped cases provide no executed assertion evidence. Only cases reported by pytest appear below; a stopped run does not establish full coverage.</p>
<div class="metrics">{badges}</div>
<p><b>Commit</b> <code>{esc(metadata['commit'])}</code> | <b>Python</b> {esc(metadata['python'])} | <b>Pytest exit code</b> {metadata['exit_code']}</p>
<p><a href="results.xml">JUnit XML</a> | <a href="console.txt">Console log</a> | <a href="summary.json">Run metadata and results</a></p>
<details><summary>Exact command</summary><pre>{esc(metadata['command'])}</pre></details>
<h2>Individual test results</h2><div class="controls"><input id="search" aria-label="Search tests" placeholder="Search by test name or module"><select id="status" aria-label="Filter result">{options}</select></div>
<p id="shown"></p><div class="tablewrap"><table><thead><tr><th>ID</th><th>Result</th><th>Test and evidence</th><th>Time</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<h2>Complete pytest output</h2><details><summary>Show console output</summary><pre>{esc(console)}</pre></details>
<script>
const search=document.querySelector('#search'), status=document.querySelector('#status');
function filter(){{let visible=0;document.querySelectorAll('tbody tr[data-status]').forEach(row=>{{
 row.hidden=!(status.value==='ALL'||row.dataset.status===status.value)||!row.textContent.toLowerCase().includes(search.value.toLowerCase());
 if(!row.hidden)visible++;
}});document.querySelector('#shown').textContent=visible+' reported test cases shown';}}
search.addEventListener('input',filter);status.addEventListener('change',filter);filter();
</script></main></body></html>'''
    (folder / "report.html").write_text(page, encoding="utf-8")
    (folder / "summary.json").write_text(json.dumps({**metadata, "counts": dict(counts), "cases": cases}, indent=2), encoding="utf-8")


def main() -> int:
    # gives the demo one command per test scope without changing application settings
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Run the DocumentationDrifter test bench and generate an HTML evidence report")
    parser.add_argument("--mode", choices=("local", "smoke", "live"), default="local")
    parser.add_argument("--url", default=RAILWAY, help="Hosted API URL used by smoke and live modes")
    parser.add_argument("--console-url", default="", help="Also test this deployed console in live mode")
    parser.add_argument("--show-known-failures", action="store_true", help="Treat existing xfail cases as ordinary failures")
    args = parser.parse_args()
    if args.console_url and args.mode != "live":
        parser.error("--console-url is used only with --mode live")
    if args.show_known_failures and args.mode == "smoke":
        parser.error("Smoke mode does not run the known frontend cases")

    start = datetime.now().astimezone()
    folder = ROOT / "testbench/results/bench" / (start.strftime("%Y%m%d-%H%M%S-%f") + "-" + args.mode)
    folder.mkdir(parents=True, exist_ok=False)
    tests = "testbench/tests" if args.mode == "local" or args.console_url else "testbench/tests/test_api.py"
    command = [sys.executable, "-m", "pytest", tests, "-v", "-ra", "--tb=short", f"--junitxml={folder / 'results.xml'}", "-p", "no:cacheprovider"]
    command += ["--website-url=" + ("" if args.mode == "local" else args.url), "--console-url=" + args.console_url]
    if args.mode == "smoke":
        command += ["-k", "not fixture_analysis_and_saved_run"]
    elif args.mode == "live":
        command += ["--maxfail=1"]
    if args.show_known_failures:
        command += ["--runxfail"]
    if args.mode == "local" or args.console_url:
        command += ["--screenshot=only-on-failure", "--tracing=retain-on-failure", "--output=" + str(folder / "browser")]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    env.pop("DRIFTER_TARGET_URL", None)
    env.pop("DRIFTER_CONSOLE_URL", None)
    env["DRIFTER_OFFLINE"] = "1" if args.mode == "local" else "0"
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "not available"
    print(f"Mode: {args.mode}\nTarget: {'local isolated servers' if args.mode == 'local' else args.url}\nEvidence folder: {folder}", flush=True)
    before = time.monotonic()
    output = []
    with (folder / "console.txt").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line)
            output.append(line)
        code = process.wait()
    cases = read_cases(folder / "results.xml")
    if not cases and code == 0:
        code = 2
    metadata = {
        "mode": args.mode, "target": "Local isolated API and console" if args.mode == "local" else args.url,
        "console_url": args.console_url, "started_at": start.isoformat(timespec="seconds"),
        "elapsed_seconds": round(time.monotonic() - before, 2), "exit_code": code,
        "python": sys.version.split()[0], "commit": commit, "command": subprocess.list2cmdline(command),
    }
    write_report(folder, metadata, cases, "".join(output))
    print(f"\nOpen this report in Chrome:\n{folder / 'report.html'}", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
