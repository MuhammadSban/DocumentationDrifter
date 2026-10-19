# 11: Analyses hang on the deployed system

**What to build:** Every analysis on the deployed system answers within its limits, so any team's tester can run the shared tests against us. On 2026-10-18 (evening) our deployed system answered health, validation errors and unknown-id lookups at once, but no analysis answered at all. A single `POST /system/analyze` for the fixture repo's `c1-impl-only` gave nothing in 200 s. Our tester's T-01 to T-05 each hit its 90 s call limit. Earlier the same day, Team 16's tester session `7db7828e-a65c-4b03-87b7-2e05d780eafe` against us still answered 409 after 20 minutes. Find out why the runs that hold the two analysis slots never finish, despite the 60 s git timeout and the 120 s analysis deadline. Then make sure a request waiting for a slot can't wait forever either: today its deadline only starts once it has a slot (`analysis.py`, `slot()` and `analyze()`).

**Blocked by:** None (can start immediately)

**Status:** ready-for-human · local timeout fixes implemented on 2026-10-18; production diagnosis and post-redeploy cross-test remain

**Spec:** docs/spec.md section 3, "Limits" (at most 2 analyses at once, extra requests wait; a git call over 60 s or an analysis over 120 s is 500 TIMEOUT); the student-facing spec, "Timing" ("The pod defines project-call time limits"); TT-Q5 (90 s per project call)

- [ ] The cause is found and written in this ticket: which call hangs, and why the 60 s and 120 s limits don't stop it.
- [x] An analysis that can't finish answers 500 `TIMEOUT` within the limits, waiting time for a slot included, and frees its slot.
- [x] A test reproduces the hang offline (for example a fake remote that never answers) and shows the slot freed afterwards.
- [ ] After a redeploy, our tester against the deployed system gets an answer to every test within the 90 s call limit, and the result is recorded in ticket 09.
- [x] The whole suite is green offline.

## Comments

**2026-10-18, resumed implementation.** Two unbounded waits are confirmed locally:

- `analysis.analyze()` acquired its semaphore without a timeout and only then started the 120 s deadline. The replacement regression failed while the slot was held; it now returns 500 `TIMEOUT` before that slot is released. The same deadline is passed through to git after acquiring a slot, and `finally` releases an acquired slot on success or failure.
- After `communicate(timeout=...)` expired, `fetch._run()` killed git and called `communicate()` again without a timeout. An escaped descendant could retain stdout or stderr and prevent that call from ever seeing EOF. A regression using real processes reproduces this: a launcher exits after starting a detached child that retains the output handles, while the original process overruns its budget. Before the fix, the API remained blocked after killing the original process; afterwards it returns 500 `TIMEOUT` and accepts another analysis. Output now goes to temporary files, so cleanup does not drain inherited output pipes. Windows `taskkill` and the final wait for git each have a 1 s cleanup timeout.

A real local HTTP remote that accepts git's request and sends no response is also tested with either the git timeout or the overall deadline expiring first. Both return `TIMEOUT`, save nothing, remove the clone and allow a later analysis. These tests open a course test session first, so coverage monitoring is active.

**Production evidence and remaining acceptance.** The initial read-only `/system/openapi.json` probe answered 200. Subsequent `/system/health` and one fixture `POST /system/analyze` each exceeded a 15 s diagnostic client timeout. Those probes do not identify which deployed git call stalled or prove it uses the escaped-pipe failure reproduced locally. No authenticated Railway browser session was available for logs. The first acceptance check remains open until the deployed stalled call is identified; the post-redeploy check remains open until Kaan deploys and runs the tester, recording its result in ticket 09. Ticket 09 explicitly reserves merge/push/deploy for Kaan, so this change is committed locally on `kaan_v1`.

**Validation so far.** The focused limits and course-route tests pass (41 passed). Mypy passes `analysis.py`; checking `fetch.py` leaves two existing nullable `_git` errors in `Comparison.read()` and `Comparison.tree()` (lines 70 and 78), verified against the starting commit. The starting version had five type errors on this Windows host; the changed subprocess code adds none. Full offline-suite and review results follow below.

**Final validation.** `DRIFTER_OFFLINE=1 .venv/Scripts/python.exe -m pytest -q --tb=short -o faulthandler_timeout=20`: 487 passed, 60 skipped, one upstream Starlette/AnyIO deprecation warning (341.67 s, Windows/Python 3.13). The escaped-output regression uses actual Git and an external remote helper, with no interception of connector commands. Bytecode compilation and whitespace checks pass. The code-review skill's parallel reviews finish with Standards: 0 remaining findings (the test-seam and comment-format findings were fixed), Spec: 0 findings. Neither open production acceptance check is claimed complete.
