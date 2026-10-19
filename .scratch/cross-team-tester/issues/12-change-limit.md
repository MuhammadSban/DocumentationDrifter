# 12: Fail a run of more than 2000 changed files the way Team 16 does

**What to build:** When a diff has more than 2000 changed files, our system saves and returns a 200 result with `status: ERROR`, empty `changes` and `skipped`, and `error` `{"code": "CHANGE_LIMIT_EXCEEDED", "message": "<n> changed files exceeds the limit of 2000"}`, as Team 16's does (TT-Q13). It is the first saved ERROR result we return, which TT-Q7 row 5 already agreed to ("a mapping problem inside a valid commit is a saved 200 result with `status: ERROR`").

**Blocked by:** None (can start immediately)

**Status:** ready-for-human · implemented (2026-10-18), not yet deployed. Committed on `kaan_test` (3ee43f3); tests in `tests/test_v1_change_limit.py`. Decided on 2026-10-18 (TT-Q13).

**Spec:** docs/plan/decisions.md, TT-Q7 row 5 and TT-Q13; Team 16's `doctracker/system/classify.py`, `analysis.py` and `mapping-v1.yaml` at `0db21ca` (`max_changed_files: 2000`)

- [x] 2001 changed files give 200 with `status: ERROR` and `CHANGE_LIMIT_EXCEEDED`, saved and served back by `GET /analysis/{id}` unchanged; 2000 give a normal SUCCESS result.
- [x] The limit is a config value, defaulting to 2000.
- [x] `docs/spec.md` drops "`SUCCESS` for every saved run" and lists the new code.
- [x] The whole suite is green offline.
