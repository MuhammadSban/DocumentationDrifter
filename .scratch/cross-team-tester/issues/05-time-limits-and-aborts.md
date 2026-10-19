# 05: Time limits, aborts and the skipped tests

**What to build:** A run never leaves a session stuck (TT-Q5, TT-Q10). Each project call has a 90 s limit, and the suite 600 s, starting with one `GET {target_url}/health` warm-up. Each result is stored as soon as it's known. When the suite limit passes or the tester fails, the test in flight becomes `error` with source `tester` (one project call that times out on its own is still `error`/`communication`), untried tests become `skip`, the report is stored, and the run answers 500 `{"message", "source": "tester"}`; `GET /test/report` then returns that report. A second `/test/run` on a session, during or after a run, is 409. T-18 to T-23 are always `skip`, with Team 16's titles, tags and reasons copied from their suite (TT-Q12): T-18 to T-20 "Documentation detection is the Phase 4 milestone (Phase 2, Section 6.2).", T-21 "Requires findings from the Phase 4 detector.", T-22 "Review workflow is the Phase 5 milestone (Phase 2, Section 6.3).", T-23 "Requires source comparison and code inspection; scheduled for Phase 5."

**Blocked by:** 01

**Status:** ready-for-human · implemented (2026-10-18), not yet deployed. Committed on `kaan_test` (fbf1b3f); tests in `tests/test_tester_limits.py`. Decided on 2026-10-18 (TT-Q5, TT-Q10, TT-Q11).

**Spec:** docs/plan/decisions.md, TT-Q5, TT-Q10, TT-Q11; the course's execution rules (Runs, Tester reports, Timing)

- [x] Both limits are config values, defaulting to 90 s and 600 s.
- [x] Against a stub target that hangs on one test, the run ends within the suite limit, that test is `error`/`tester`, the later ones `skip`, and `GET /test/report` returns the same body.
- [x] A concurrent or repeated `/test/run` on one session gets 409, including after an abort, doesn't start a second suite, and leaves the stored report unchanged.
- [x] T-18 to T-23 appear in every report as `skip` with a reason.
- [x] The registry's run notes text (setup, run and system-setup limits) is written in the README, for ticket 09 to copy.
- [x] The whole suite is green offline.

## Comments

**2026-10-18, revised against the student-facing spec and TT-Q12.** The spec says "mark tests prevented by the abort error with source tester, and mark unexecuted tests skip", so the test cut off by the suite limit is `error`/`tester`, not `communication`. It also says "Reject concurrent or later tester runs with 409, including after an abort" and "Keep the report unchanged once the suite ends". Today a second run reruns the suite and overwrites the report. T-18 to T-23 take Team 16's exact titles, tags and skip reasons from their suite, and "Include every planned test exactly once" means all 23 appear in every report.
