# 02: Shared tests T-08 to T-17: errors, saved results and repeatability

**What to build:** The tester runs T-08 to T-17 with the same meanings as Team 16's tester, judged by TT-Q9. Error tests pass on the expected HTTP status and error `code` plus a non-empty `message`, never on wording. The saved-result tests analyse a fixture commit on `ParthGupta06/doc-tracker-fixtures` (by default `c1-impl-only`, `add930c827b4f242d173fe6d26ebc068c8dd65fb`, unless Team 16's tester uses another).

| Test | Request | Pass when |
|---|---|---|
| T-08 | `/analyze` without `commit_id` | 400 `INVALID_REQUEST` |
| T-09 | malformed JSON body | 400 `INVALID_REQUEST` |
| T-10 | `repository` not in owner/name form | 400 `INVALID_REQUEST` |
| T-11 | `commit_id` of the wrong type | 400 `INVALID_REQUEST` |
| T-12 | a repository that doesn't exist | 404 `REPOSITORY_NOT_FOUND` |
| T-13 | a commit that doesn't exist in the fixture repo | 404 `COMMIT_NOT_FOUND` |
| T-14 | analyse, then `GET /analysis/{id}` | the GET body equals the POST body |
| T-15 | `GET /analysis/{unknown id}` | 404 `ANALYSIS_NOT_FOUND` (from ticket 01) |
| T-16 | the same analysis twice | two different ids, both retrievable unchanged |
| T-17 | the same analysis five times | every field equal except `analysis_id` and `created_at`, each result schema-valid |

A 5xx the contract doesn't list is `error` with source `system`; no response within the call limit is `error` with source `communication`.

**Blocked by:** 01

**Status:** ready-for-human · implemented (2026-10-18), not yet deployed. T-08 to T-17 run in order in `Source/Tester/suite.py`, with the fixture commit (`c1-impl-only`, full SHA) and the repository named once at the top. Offline, the in-process `/system` analyses a local copy of the fixture repo, `tests/data/doc-tracker-fixtures.bundle`, which holds the same SHAs as GitHub; all ten pass. `tests/test_tester_shared_tests.py` breaks each rule on a stub one at a time. Readings taken: only a 500 with `TIMEOUT` or `WRITE_FAILED` (the pod contract's 500 codes) is a `fail`; any other 5xx, `LLM_UNAVAILABLE` included, is `error`/`system`. T-14, T-16 and T-17 all require a schema-valid result (fields, item shapes and enums), not only T-17. The tests for T-12 and T-13 use `ParthGupta06/no-such-repository` and `deadbeef` x5, since Team 16's tester's exact requests aren't known. Decided on 2026-10-18 (TT-Q9).

**Spec:** docs/plan/decisions.md, TT-Q8 and TT-Q9; docs/vision/phase2-specification.txt §4.1 (AC-06, AC-07, AC-08, AC-10) and §5.1

- [x] T-08 to T-17 run in order, each giving `pass`, `fail` or `error` with a message that states what was expected and what came back.
- [x] Error tests never compare message wording, and fail an empty `message`.
- [ ] T-17 keeps `tool_version` in the comparison. (Dropped by TT-Q12: Team 16's T-17 doesn't compare it.)
- [x] The analyses use the fixture commit by full SHA, and the commit is named in one place.
- [x] Against the in-process `/system`, all ten pass offline using a local copy of the fixture commit; against a stub that breaks each rule, each test fails or errors as specified.
- [x] The whole suite is green offline.

## Comments

**2026-10-18, TT-Q12.** Realigned to Team 16's suite, which overrides parts of this ticket: T-09 to T-13 and T-15 send their exact requests; T-14 analyses `c1-impl-only`, T-16 `c2-add-mod-del` and T-17 `c4-categories`; T-17 compares only repository, head and base commits, status, changes, skipped and findings without `finding_id`, so the "T-17 keeps `tool_version`" box no longer holds; any 5xx is `error`/`system` (the listed-500 reading is gone); every analysis needs `status: SUCCESS`; and the schema check is theirs.
