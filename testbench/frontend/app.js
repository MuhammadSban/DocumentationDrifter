// connects the dashboard to actual runner jobs and saved test evidence
"use strict";

const $ = selector => document.querySelector(selector);
const state = {run: null, runs: [], filter: "ALL", offset: 0, jobId: null, job: null, polling: false, selecting: 0};
const disconnectMessage = "Connection lost. Reconnecting to the dashboard; the last observed run status may be stale.";
const labels = {local: "Local suite", smoke: "Smoke check", live: "Live analysis"};
const descriptions = {
  local: "Starts isolated local services with controlled LLM output. No API key needed.",
  smoke: "Checks your hosted API without submitting analyses. Creates one unique course test session.",
  live: "Runs fixture analyses on your deployment and checks saved results. Uses the deployment’s real LLM provider and may take several minutes."
};

function setError(message = "") {
  $("#error-banner").textContent = message;
  $("#error-banner").hidden = !message;
}

async function api(url, options = {}) {
  const response = await fetch(url, {cache: "no-store", ...options});
  const data = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map(item => item.msg).join("; ") : data.detail;
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return data;
}

function count(counts, key) { return Number(counts?.[key]) || 0; }
function seconds(value) { return `${Number(value || 0).toFixed(1)}s`; }
function date(value) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Unknown time" : parsed.toLocaleString(undefined, {month: "short", day: "numeric", hour: "numeric", minute: "2-digit"});
}

function verdict(run) {
  if (run.exit_code !== 0) return ["Run failed", "failed"];
  if (!run.cases?.length && !run.case_count) return ["No case evidence", "neutral"];
  if (count(run.counts, "KNOWN FAILURE")) return ["Known defects reproduced", "known"];
  if (count(run.counts, "SKIP")) return ["Completed with skips", "skip"];
  return ["All recorded cases passed", "pass"];
}

function pill(text, kind) {
  const element = document.createElement("span");
  element.className = `pill ${kind}`;
  element.textContent = text;
  return element;
}

function modeChanged() {
  const mode = $("input[name=mode]:checked").value;
  $("#target-field").hidden = mode === "local";
  $("#target-url").required = mode !== "local";
  $("#target-url").disabled = mode === "local";
  $("#console-field").hidden = mode !== "live";
  $("#console-url").disabled = mode !== "live";
  $("#known-field").hidden = mode === "smoke";
  $("#show-known").disabled = mode === "smoke";
  $("#mode-description").textContent = descriptions[mode];
  $("#scope-note").textContent = mode === "local"
    ? "Local runs exercise the real API, Git comparisons, saved results, and console. Controlled LLM output keeps runs repeatable."
    : mode === "smoke"
      ? "Smoke checks verify basic hosted HTTP behavior. A passing smoke run does not establish that analyses can finish."
      : "Live mode submits real analyses to the chosen deployment. Provider errors and timeouts remain failures; no LLM replacement is applied.";
  if (!state.job || state.job.status !== "running") $("#run-button-label").textContent = `Run ${labels[mode].toLowerCase()}`;
}

async function refreshHistory(selectNewest = false) {
  const data = await api("/api/runs");
  state.runs = data.runs;
  renderHistory();
  if (selectNewest && state.runs.length) await selectRun(state.runs[0].id);
  else if (!state.run && !state.runs.length) {
    $("#summary-title").textContent = "Your first run is ready to begin";
    $("#run-verdict").textContent = "No runs yet";
  }
}

function renderHistory() {
  const fragment = document.createDocumentFragment();
  for (const run of state.runs) {
    const row = document.createElement("tr");
    row.classList.toggle("selected", state.run?.id === run.id);
    const started = document.createElement("td"); started.textContent = date(run.started_at); row.append(started);
    const mode = document.createElement("td"); mode.textContent = labels[run.mode] || run.mode; row.append(mode);
    const outcome = document.createElement("td"); outcome.append(pill(...verdict(run))); row.append(outcome);
    const total = document.createElement("td"); total.textContent = run.case_count; row.append(total);
    const elapsed = document.createElement("td"); elapsed.className = "mono"; elapsed.textContent = seconds(run.elapsed_seconds); row.append(elapsed);
    const action = document.createElement("td");
    const button = document.createElement("button"); button.type = "button"; button.className = "view-run"; button.textContent = "View results ↗";
    button.setAttribute("aria-label", `View ${labels[run.mode] || run.mode} results from ${date(run.started_at)}`);
    button.addEventListener("click", async () => {
      try { await selectRun(run.id); $("#results").scrollIntoView({behavior: "smooth"}); }
      catch (error) { setError(error.message); }
    });
    action.append(button); row.append(action); fragment.append(row);
  }
  $("#history-rows").replaceChildren(fragment);
  $("#history-empty").hidden = state.runs.length > 0;
}

async function selectRun(id) {
  const selection = ++state.selecting;
  const run = await api(`/api/runs/${encodeURIComponent(id)}`);
  if (selection !== state.selecting) return;
  state.run = run;
  const counts = run.counts;
  $("#summary-title").textContent = `${labels[run.mode] || run.mode} · ${date(run.started_at)}`;
  const [text, kind] = verdict(run);
  $("#run-verdict").textContent = text; $("#run-verdict").className = `pill ${kind}`;
  $("#metric-total").textContent = run.cases.length;
  $("#metric-pass").textContent = count(counts, "PASS");
  $("#metric-fail").textContent = count(counts, "FAIL") + count(counts, "ERROR");
  $("#metric-known").textContent = count(counts, "KNOWN FAILURE");
  $("#summary-meta").textContent = `${seconds(run.elapsed_seconds)} elapsed · ${count(counts, "SKIP")} skipped · Commit ${(run.commit || "unknown").slice(0, 7)} · ${run.target || "Unknown target"}`;
  $("#summary-report").hidden = !run.artifacts["report.html"];
  $("#summary-report").href = run.artifacts["report.html"] || "#";
  $("#result-count").textContent = run.cases.length;
  $("#count-all").textContent = run.cases.length;
  $("#count-pass").textContent = count(counts, "PASS");
  $("#count-failed").textContent = count(counts, "FAIL") + count(counts, "ERROR");
  $("#count-known").textContent = count(counts, "KNOWN FAILURE");
  $("#count-skip").textContent = count(counts, "SKIP");
  const links = document.createDocumentFragment();
  for (const [file, label] of [["report.html", "HTML ↗"], ["results.xml", "XML ↓"], ["summary.json", "JSON ↓"], ["console.txt", "Log ↓"]]) {
    if (!run.artifacts[file]) continue;
    const link = document.createElement("a"); link.href = run.artifacts[file]; link.textContent = label;
    if (file === "report.html") { link.target = "_blank"; link.rel = "noopener"; }
    else { link.download = file; }
    links.append(link);
  }
  $("#artifact-links").replaceChildren(links);
  renderCases(); renderHistory();
}

function renderCases() {
  const cases = state.run?.cases || [];
  const query = $("#case-search").value.trim().toLowerCase();
  const fragment = document.createDocumentFragment();
  let visible = 0;
  cases.forEach((test, index) => {
    const statusMatch = state.filter === "ALL" || test.status === state.filter || state.filter === "FAILED" && ["FAIL", "ERROR"].includes(test.status);
    if (!statusMatch || !`${test.name} ${test.module} ${test.detail}`.toLowerCase().includes(query)) return;
    visible++;
    const row = document.createElement("tr");
    const id = document.createElement("td"); id.textContent = `TB${String(index + 1).padStart(3, "0")}`; row.append(id);
    const name = document.createElement("td");
    const button = document.createElement("button"); button.type = "button"; button.className = "case-name";
    button.textContent = test.name.replace(/^test_/, "").replaceAll("_", " "); button.addEventListener("click", () => showCase(test)); name.append(button);
    const module = document.createElement("span"); module.className = "case-module"; module.textContent = test.module; name.append(module); row.append(name);
    const status = document.createElement("td"); status.append(pill(test.status === "KNOWN FAILURE" ? "Known defect" : test.status === "PASS" ? "Passed" : test.status === "SKIP" ? "Skipped" : test.status, test.status.toLowerCase().replaceAll(" ", "-"))); row.append(status);
    const duration = document.createElement("td"); duration.className = "mono"; duration.textContent = seconds(test.seconds); row.append(duration);
    const details = document.createElement("td"); const arrow = document.createElement("button"); arrow.type = "button"; arrow.textContent = "›"; arrow.className = "detail-button"; arrow.setAttribute("aria-label", `Details for ${test.name}`); arrow.addEventListener("click", () => showCase(test)); details.append(arrow); row.append(details);
    fragment.append(row);
  });
  $("#case-rows").replaceChildren(fragment);
  $("#results-empty").hidden = visible > 0;
  $("#results-empty h3").textContent = cases.length ? "No matching test cases" : "No results to display";
  $("#results-empty p").textContent = cases.length ? "Try another search or result filter." : "Run the suite or select a saved run below.";
  $("#visible-count").textContent = `${visible} of ${cases.length} test cases`;
  document.querySelectorAll(".filter").forEach(button => {
    const active = button.dataset.status === state.filter;
    button.classList.toggle("active", active); button.setAttribute("aria-pressed", String(active));
  });
}

function showCase(test) {
  $("#detail-name").textContent = test.name;
  $("#detail-module").textContent = test.module;
  $("#detail-status").textContent = test.status;
  $("#detail-status").className = `pill ${test.status.toLowerCase().replaceAll(" ", "-")}`;
  $("#detail-time").textContent = `${seconds(test.seconds)} elapsed`;
  $("#detail-output").textContent = test.detail || "No assertion detail was recorded.";
  $("#case-dialog").showModal();
}

function updateJob(data) {
  if (!data.job) return;
  const job = data.job;
  const changedJob = state.jobId !== job.id;
  const wasRunning = !changedJob && state.job?.status === "running";
  if (changedJob) {
    state.jobId = job.id;
    state.offset = 0;
    $("#console-output").textContent = "";
  }
  if (data.log) $("#console-output").textContent += data.log;
  state.offset = data.offset;
  state.job = job;
  const running = job.status === "running";
  $("#run-fields").disabled = running;
  $("#run-button-label").textContent = running ? "Running suite…" : `Run ${labels[$("input[name=mode]:checked").value].toLowerCase()}`;
  $("#job-status").textContent = running ? "Running" : job.status === "completed" ? "Finished" : job.status === "cancelled" ? "Cancelled" : "Failed";
  $("#job-status").className = `pill ${job.status}`;
  $("#job-message").textContent = running ? `${labels[job.mode]} in progress` : job.status === "cancelled" ? "Run cancelled. Partial output is not a completed result." : job.status === "completed" ? "Execution finished. Review the recorded outcomes." : "Execution failed. Inspect the output and result details.";
  $("#job-duration").textContent = seconds(job.elapsed_seconds);
  $("#execution-note").textContent = running ? "Streaming actual runner output" : `Exit code ${job.exit_code ?? "—"}`;
  $("#progress-track").hidden = !running;
  $("#cancel-button").hidden = !running;
  $("#cancel-button").disabled = !!job.cancel_requested;
  $("#cancel-button").textContent = job.cancel_requested ? "Cancelling…" : "Cancel run";
  if ($("#auto-scroll").checked) $("#console-output").scrollTop = $("#console-output").scrollHeight;
  if (!running && (wasRunning || changedJob)) finishJob(job).catch(error => setError(error.message));
}

async function finishJob(job) {
  await refreshHistory();
  if (job.run_id && state.runs.some(run => run.id === job.run_id)) await selectRun(job.run_id);
}

async function poll() {
  if (state.polling) return;
  state.polling = true;
  try {
    let data = await api(`/api/job?offset=${state.offset}`);
    if (data.job && data.job.id !== state.jobId && state.offset) data = await api("/api/job?offset=0");
    updateJob(data);
    $("#connection").textContent = "Connected"; $("#connection-dot").classList.remove("offline");
    if ($("#error-banner").textContent === disconnectMessage) setError();
  } catch {
    $("#connection").textContent = "Disconnected"; $("#connection-dot").classList.add("offline");
    if (state.job?.status === "running") setError(disconnectMessage);
  } finally { state.polling = false; }
}

$("#run-form").addEventListener("submit", async event => {
  event.preventDefault(); setError();
  const mode = $("input[name=mode]:checked").value;
  const request = {mode, url: mode === "local" ? "" : $("#target-url").value, console_url: mode === "live" ? $("#console-url").value : "", show_known_failures: mode !== "smoke" && $("#show-known").checked};
  $("#run-fields").disabled = true;
  try {
    const data = await api("/api/runs", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(request)});
    updateJob(data);
  } catch (error) {
    $("#run-fields").disabled = state.job?.status === "running";
    setError(error.message);
  }
});

document.querySelectorAll("input[name=mode]").forEach(input => input.addEventListener("change", modeChanged));
document.querySelectorAll(".filter").forEach(button => button.addEventListener("click", () => { state.filter = button.dataset.status; renderCases(); }));
$("#case-search").addEventListener("input", renderCases);
$("#close-dialog").addEventListener("click", () => $("#case-dialog").close());
$("#case-dialog").addEventListener("click", event => { if (event.target === $("#case-dialog")) { const rect = event.target.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) event.target.close(); } });
$("#refresh-history").addEventListener("click", async () => { try { setError(); await refreshHistory(!state.run); } catch (error) { setError(error.message); } });
$("#cancel-button").addEventListener("click", async () => {
  $("#cancel-button").disabled = true;
  try { await api("/api/job/cancel", {method: "POST"}); await poll(); }
  catch (error) { setError(error.message); $("#cancel-button").disabled = false; }
});
$("#copy-log").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText($("#console-output").textContent); $("#copy-log").textContent = "Copied"; setTimeout(() => $("#copy-log").textContent = "Copy output", 1500); }
  catch { setError("Clipboard access is unavailable. Select the output text to copy it."); }
});
document.querySelectorAll(".nav-link").forEach(link => link.addEventListener("click", () => { document.querySelectorAll(".nav-link").forEach(item => item.classList.toggle("active", item === link)); }));

async function init() {
  modeChanged(); renderCases();
  try {
    const config = await api("/api/config");
    $("#target-url").value = config.default_url;
    $("#python-version").textContent = `Python ${config.python}`;
    await refreshHistory(true);
    await poll();
  } catch (error) { setError(`Could not load the dashboard: ${error.message}. Check that the local server is running.`); }
  setInterval(poll, 1000);
}
init();
