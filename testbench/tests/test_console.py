# exercises the actual console in a browser, keeping GitHub responses deterministic

from __future__ import annotations

import json

import pytest

pw = pytest.importorskip("playwright.sync_api", reason="Install testbench/requirements.txt to run browser tests")
expect = pw.expect
pytestmark = pytest.mark.website

BASE = "a" * 40
HEAD = "b" * 40
REPO = "octo/demo"
STORE = "drifter.watchlist.v1"


def _run(repository=REPO, path="src/app.py", analysis_id="an-" + "1" * 32):
    # supplies a v1.1 run with a rename and a skipped file for the rendered tables
    return {
        "analysis_id": analysis_id, "repository": repository,
        "head_commit": HEAD, "base_commit": BASE, "config_version": "test-rules", "tool_version": "1.1.0",
        "status": "SUCCESS", "error": None, "issues": [], "created_at": "2026-10-18T12:00:00.000Z",
        "changes": [
            {"path": path, "old_path": "src/old.py", "change_type": "RENAMED", "category": "IMPLEMENTATION"},
            {"path": "assets/logo.png", "old_path": None, "change_type": "ADDED", "category": "OTHER"},
        ],
        "skipped": [{"path": "assets/logo.png", "reason": "UNSUPPORTED_FILE_TYPE"}],
    }


def _json(route, body, status=200, headers=None):
    route.fulfill(status=status, content_type="application/json", body=json.dumps(body), headers=headers)


def _watch(page, repository=REPO, base=BASE):
    page.get_by_label("Repository owner and name").fill(repository)
    page.get_by_label("Commit SHA").fill(base)
    page.get_by_role("button", name="Watch", exact=True).click()


def _select(page, repository=REPO):
    page.locator("#rows .row").filter(has=page.locator(".name", has_text=repository)).click()


def _seed(page, repos, paused=True):
    # opens saved watch state through the same storage boundary used after a reload
    data = {"repos": repos, "paused": paused, "interval": 300, "api": ""}
    page.evaluate("([key,data]) => localStorage.setItem(key, JSON.stringify(data))", [STORE, data])
    page.reload()


@pytest.fixture
def console(page, console_url):
    # blocks accidental public GitHub calls until a test supplies its own response
    page.route("https://api.github.com/**", lambda route: route.abort())
    page.goto(console_url)
    expect(page.get_by_role("heading", name="Add repository")).to_be_visible()
    return page


def test_initial_console_is_ready(console):
    expect(console).to_have_title("DocumentationDrifter Console")
    expect(console.get_by_text("No repositories watched yet.")).to_be_visible()
    expect(console.locator("#count")).to_have_text("0 repositories")


@pytest.mark.parametrize("repository,sha,message", [
    ("invalid", BASE, "repository must use the format owner/name"),
    (REPO, "123", "commit_id must be a 7-40 character hexadecimal commit SHA"),
], ids=["repository-format", "sha-format"])
def test_invalid_watch_input_stays_out_of_list(console, repository, sha, message):
    _watch(console, repository, sha)
    expect(console.locator("#f-err")).to_have_text(message)
    expect(console.locator("#rows .row")).to_have_count(0)


def test_duplicate_repository_is_rejected(console):
    _watch(console)
    _watch(console)
    expect(console.locator("#f-err")).to_have_text("already watching " + REPO)
    expect(console.locator("#rows .row")).to_have_count(1)


def test_watch_list_persists_and_can_be_paused_and_removed(console):
    _watch(console)
    console.locator("#pause").click()
    console.reload()
    expect(console.locator("#rows .name")).to_have_text(REPO)
    expect(console.locator("#pause")).to_have_text("resume")
    row = console.locator("#rows .row")
    row.hover()
    row.get_by_title("Pause", exact=True).click()
    expect(row.locator(".sub")).to_have_text("paused")
    row.hover()
    row.get_by_title("Remove", exact=True).click()
    expect(console.locator("#rows .row")).to_have_count(0)
    expect(console.get_by_text("No repositories watched yet.")).to_be_visible()


def test_changed_head_sends_correct_request_and_renders_run(console):
    run = _run()
    console.route("https://api.github.com/**", lambda route: _json(route, [{"sha": HEAD}]))
    console.route("**/system/analyze", lambda route: _json(route, run))
    console.route("**/system/analysis/*", lambda route: _json(route, run))
    _watch(console)
    _select(console)
    with console.expect_request("**/system/analyze") as pending:
        console.locator("#poll").click()
    assert pending.value.post_data_json == {"repository": REPO, "commit_id": HEAD, "base_commit": BASE}
    expect(console.locator("#detail .trow")).to_have_count(2)
    expect(console.locator("#detail")).to_contain_text("src/app.py")
    expect(console.locator("#detail")).to_contain_text("src/old.py")
    expect(console.locator("#detail")).to_contain_text("IMPLEMENTATION")
    expect(console.locator("#detail .skip")).to_contain_text("UNSUPPORTED_FILE_TYPE")
    expect(console.locator("#detail .counters b")).to_have_text(["2", "1", "0"])
    expect(console.locator("#detail .meta")).to_contain_text(run["analysis_id"])
    assert console.evaluate("key => JSON.parse(localStorage.getItem(key)).repos[0].base", STORE) == HEAD
    console.reload()
    _select(console)
    expect(console.locator("#detail .trow")).to_have_count(2)


def test_unchanged_head_does_not_analyze(console):
    requests = []
    console.route("https://api.github.com/**", lambda route: _json(route, [{"sha": BASE}]))
    console.route("**/system/analyze", lambda route: (requests.append(route.request), _json(route, _run())))
    _watch(console)
    console.locator("#poll").click()
    expect(console.locator("#rows .sub")).to_contain_text("up to date")
    assert requests == []


@pytest.mark.parametrize("code,message", [
    ("COMMIT_NOT_FOUND", "commit was not found"),
    ("TIMEOUT", "The analysis took longer than 120 s"),
    ("WRITE_FAILED", "The run file could not be saved"),
])
def test_analysis_error_is_visible_and_keeps_previous_base(console, code, message):
    console.route("https://api.github.com/**", lambda route: _json(route, [{"sha": HEAD}]))
    console.route("**/system/analyze", lambda route: _json(route, {"code": code, "message": message}, 500 if code != "COMMIT_NOT_FOUND" else 404))
    _watch(console)
    _select(console)
    console.locator("#poll").click()
    expect(console.locator("#detail .notice")).to_contain_text(code)
    expect(console.locator("#detail .notice")).to_contain_text(message)
    expect(console.get_by_role("button", name="Retry", exact=True)).to_be_visible()
    assert console.evaluate("key => JSON.parse(localStorage.getItem(key)).repos[0].base", STORE) == BASE


def test_missing_github_repository_is_visible(console):
    console.route("https://api.github.com/**", lambda route: _json(route, {"message": "Not Found"}, 404))
    _watch(console)
    console.locator("#poll").click()
    expect(console.locator("#rows .sub")).to_have_text("REPOSITORY_NOT_FOUND")


def test_expired_saved_run_offers_reanalysis(console):
    console.route("**/system/analysis/*", lambda route: _json(route, {"code": "ANALYSIS_NOT_FOUND"}, 404))
    _seed(console, [{"repo": REPO, "base": HEAD, "runId": "an-" + "1" * 32}])
    _select(console)
    expect(console.get_by_text("RUN EXPIRED", exact=True)).to_be_visible()
    expect(console.get_by_role("button", name="Re-analyze", exact=True)).to_be_visible()


def test_browser_reaches_real_analysis_through_console_proxy(console, website_cases):
    repository, labels = website_cases
    case = labels["modified"]
    expected = case["expect"]
    console.route("https://api.github.com/**", lambda route: _json(route, [{"sha": expected["head_commit"]}]))
    _watch(console, repository, expected["base_commit"])
    _select(console, repository)
    with console.expect_response("**/system/analyze", timeout=180_000) as pending:
        console.locator("#poll").click()
    assert pending.value.status == 200, pending.value.text()
    body = pending.value.json()
    assert body["changes"] == expected["changes"]
    expect(console.locator("#detail .trow")).to_have_count(1)
    expect(console.locator("#detail")).to_contain_text("src/app.py")
    expect(console.locator("#detail .meta")).to_contain_text(body["analysis_id"])


def _known_defect(request, reason):
    # marks only the target assertion after the test's prerequisites have succeeded
    request.node.add_marker(pytest.mark.xfail(strict=True, raises=AssertionError, reason=reason))


def test_expired_run_can_be_recreated_without_a_new_commit(console, request):
    console.route("**/system/analysis/*", lambda route: _json(route, {}, 404))
    console.route("https://api.github.com/**", lambda route: _json(route, [{"sha": HEAD}]))
    console.route("**/system/analyze", lambda route: _json(route, _run()))
    _seed(console, [{"repo": REPO, "base": HEAD, "runId": "an-" + "1" * 32}], paused=False)
    _select(console)
    console.get_by_role("button", name="Re-analyze", exact=True).click()
    _known_defect(request, "OBS05: unchanged head prevents expired run recovery")
    expect(console.locator("#detail .trow")).to_have_count(2, timeout=1000)


def test_polling_recovers_after_github_rate_reset(console, request):
    console.clock.install()
    calls = []
    def github(route):
        calls.append(route.request)
        headers = {"access-control-allow-origin": "*", "access-control-expose-headers": "x-ratelimit-remaining, x-ratelimit-reset"}
        if len(calls) == 1:
            reset = int(console.evaluate("Date.now() / 1000")) + 1
            _json(route, {"message": "rate limit"}, 403, {**headers, "x-ratelimit-remaining": "0", "x-ratelimit-reset": str(reset)})
        else:
            _json(route, [{"sha": BASE}], headers={**headers, "x-ratelimit-remaining": "59"})
    console.route("https://api.github.com/**", github)
    _watch(console)
    console.locator("#poll").click()
    expect(console.locator("#rows .sub")).to_contain_text("rate limited")
    expect(console.locator("#rate")).to_have_text("0 / 60")
    assert len(calls) == 1
    console.clock.fast_forward(2000)
    console.locator("#poll").click()
    _known_defect(request, "OBS06: polling never clears an expired rate limit")
    expect(console.locator("#rows .sub")).to_contain_text("up to date", timeout=1000)


def test_slow_previous_selection_does_not_replace_current_result(console, request):
    delayed = []
    run_a = _run("a/one", "src/one.py", "an-" + "1" * 32)
    run_b = _run("b/two", "src/two.py", "an-" + "2" * 32)
    def saved(route):
        if route.request.url.endswith(run_a["analysis_id"]):
            delayed.append(route)
        else:
            _json(route, run_b)
    console.route("**/system/analysis/*", saved)
    _seed(console, [{"repo": "a/one", "base": BASE, "runId": run_a["analysis_id"]}, {"repo": "b/two", "base": BASE, "runId": run_b["analysis_id"]}])
    with console.expect_request("**/system/analysis/" + run_a["analysis_id"]):
        _select(console, "a/one")
    _select(console, "b/two")
    expect(console.locator("#detail")).to_contain_text("src/two.py")
    assert len(delayed) == 1
    with console.expect_response("**/system/analysis/" + run_a["analysis_id"]):
        _json(delayed[0], run_a)
    _known_defect(request, "OBS07: a stale GET overwrites the selected repository result")
    expect(console.locator("#detail")).not_to_contain_text("src/one.py", timeout=1000)
    expect(console.locator("#detail")).to_contain_text("src/two.py", timeout=1000)


def test_second_poll_does_not_duplicate_an_inflight_analysis(console, request):
    delayed = []
    console.route("https://api.github.com/**", lambda route: _json(route, [{"sha": HEAD}]))
    console.route("**/system/analyze", lambda route: delayed.append(route))
    _watch(console)
    with console.expect_request("**/system/analyze"):
        console.locator("#poll").click()
    duplicate = False
    try:
        with console.expect_request("**/system/analyze", timeout=1000):
            console.locator("#poll").click()
        duplicate = True
    except pw.TimeoutError:
        pass
    finally:
        for route in delayed:
            _json(route, _run())
    _known_defect(request, "OBS08: overlapping polls submit duplicate analyses")
    assert not duplicate, "A second poll submitted another analysis before the first completed"
