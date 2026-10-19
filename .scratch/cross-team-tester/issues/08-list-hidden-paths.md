# 08: List hidden paths in changes[]

**What to build:** Our system reports dot-paths such as `.github/workflows/ci.yaml` and `.gitignore` in `changes[]`, classified and skipped by the same rules as any other path, as Team 16's does, and a rename across a hidden path is one RENAMED change (TT-Q7 row 9, TT-Q13).

**Blocked by:** None (can start immediately)

**Status:** ready-for-human · implemented (2026-10-18), not yet deployed. Dot-paths use the ordinary category and skip rules, cross-hidden renames retain `old_path`, and the conformance exemption is removed. The internal fixture expectations and current docs are updated; Kaan republishes the manifest.

**Spec:** docs/plan/decisions.md, TT-Q7 row 9 and TT-Q13; Team 16's `doctracker/system/classify.py`, `analysis.py` and `mapping-v1.yaml` at `0db21ca`

- [x] Hidden paths appear in `changes[]`, and in `skipped[]` only by ticket 06's rule (`.gitignore` has no supported extension, so it is skipped).
- [x] A rename into or out of a hidden path is one RENAMED change with `old_path` set.
- [x] The hidden-path known difference leaves `tests/reference.py`, `docs/spec.md` and the README, and `CONTEXT.md` drops "Ignored path".
- [x] The internal test repo's expected answers are updated; republishing waits for Kaan.
- [x] The whole suite is green offline.

## Comments


**2026-10-18, checked against TT-Q12.** No test in Team 16's suite touches a hidden path, and the fixture repo has none, so there's no agreed behaviour to match yet. It stays needs-info until Team 16 answers row 9 or a shared test covers it.

**2026-10-18, unblocked (TT-Q13).** Same answers for any file means we don't wait for Team 16 to answer row 9: their system already lists hidden paths (`analysis.py` filters nothing).

**2026-10-18, implemented.** Removed the dot-segment filter from the connector's file and change listings, keeping its mode checks. The first `/system/analyze` regression failed because the hidden paths were missing, then passed with the filter removed. API tests cover a first audit and an explicit base, ordinary categories for hidden code and docs, name-based skips, hidden modifications and deletions, hidden submodules, and renames into and out of hidden folders. Reference comparisons now compare dot-paths and their rename origins without rewriting them. The `hidden-paths`, `renames-across-hidden` and `mixed` manifest expectations match the new behavior; the mixed-case invariant requires every touched path to appear.

**Validation.** The full offline suite passes: 502 passed, 60 skipped, one upstream Starlette/AnyIO deprecation warning (350.71 s, Windows/Python 3.13). Bytecode compilation and whitespace checks pass. Mypy leaves the same two pre-existing nullable `_git` errors in `Comparison.read()` and `Comparison.tree()` (fetch.py lines 70 and 78), with no new errors. The code-review skill's parallel reviews report Standards: 0 findings; Spec: 0 findings, against `fbf1b3f`.

**Publication.** Only the generated manifest commit changes in the internal test-repo builder; the fixture step contents and SHAs are unchanged. Kaan republishes the updated manifest and deploys the service, as this ticket and ticket 09 specify.
