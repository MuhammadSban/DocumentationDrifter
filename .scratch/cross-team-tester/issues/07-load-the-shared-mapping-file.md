# 07: Classify with Team 16's categories, no DOCUMENTATION

**What to build:** Our system's categories match Team 16's for any path, with our own rules (TT-Q12, TT-Q13). DOCUMENTATION leaves the `Category` enum of `Change.category` and `Finding.change_category`, and `/system/openapi.json`. The rules give the same answers as their `mapping-v1.yaml`, checked in order, case-sensitive, first match wins, OTHER otherwise: REQUIREMENT for `requirements/**`, `docs/requirements/**`, `**/REQUIREMENTS*.md`; SPECIFICATION for `spec/**`, `specs/**`, `docs/spec/**`, `docs/specs/**`, `**/openapi*.yaml`, `**/openapi*.yml`, `**/openapi*.json`; ARCHITECTURE for `docs/architecture/**`, `**/ARCHITECTURE*.md`, `**/model_config.*`; DESIGN for `docs/design/**`, `docs/adr/**`, `**/DESIGN*.md`; IMPLEMENTATION for `*.py`, `*.ipynb`, `*.js`, `*.ts`, `*.java`, `*.c`, `*.h`, `*.cpp`, `*.hpp`, `*.go`, `*.rs`, `*.rb`, `*.sh` and `*.sql` in any folder. Here `**/` also matches no folder, and `*` stays within one segment. So doc files are OTHER and `requirements.txt` is OTHER. The patterns live in our own `path_rules.json`, and the matcher is ours. `config_version` keeps our own value, because no shared test checks it.

**Blocked by:** None (can start immediately)

**Status:** ready-for-human · implemented (2026-10-18), not yet deployed. `Category` has Team 16's six values and our `/system/openapi.json` now matches their contract with no allowed difference. `rules.matches` is our own segment-by-segment matcher over the patterns in `path_rules.json` (Python 3.12 has no `PurePath.full_match`, so the image can't use it). A review compared it with Team 16's matcher on 1124 generated paths; they disagree only on paths containing a newline, where their regex's `$` and `.` behave differently, and on a `**` that isn't a whole segment, which no rule uses. Both are left as they are, for Kaan to decide. Our tester passes T-01 to T-07 against the in-process system. Decided on 2026-10-18 (TT-Q12 and TT-Q13, which supersede TT-Q7 rows 3 and 6 for now).

**Spec:** docs/plan/decisions.md, TT-Q1 and TT-Q12; the student-facing spec ("Within a pod, project paths, methods, inputs, responses, and behavior must match the shared specification. Teams choose their internal implementations."); Team 16's system OpenAPI v0.3.0 (`tests/data/reference-openapi.json`) and tester (`doctracker/tester/suite.py` at `0db21ca`)

- [x] `Category` has exactly Team 16's six values (IMPLEMENTATION, DESIGN, ARCHITECTURE, SPECIFICATION, REQUIREMENT, OTHER), and `/system/openapi.json` shows no difference from `tests/data/reference-openapi.json` in the shared models.
- [x] Every pattern above has a test of its own (a match, a near miss, and `**/` with no folder).
- [x] Against the in-process system, our tester passes T-02, T-04 and T-06 on the local fixture copy, and T-01, T-03 and T-07 still pass.
- [x] The DOCUMENTATION known differences (`KNOWN_CATEGORY_SWAPS`, `KNOWN_SCHEMA_EXTRAS`) leave `tests/reference.py`, and `docs/spec.md` and the README no longer name DOCUMENTATION.
- [x] `CONTEXT.md` and `docs/spec.md` say what each category covers under the new rules.
- [x] The internal test repo's expected answers (`tools/testrepo.py`) are updated; republishing it waits for Kaan.
- [x] The whole suite is green offline.

## Comments

**2026-10-18, revised (TT-Q12).** This ticket used to load the pod's `mapping-v1.1.yaml` verbatim, keep DOCUMENTATION at the lowest precedence, and wait for Team 16 to publish the file. Team 16 agrees only to what their test suite checks. Their contract has no DOCUMENTATION and their tester expects doc files as OTHER, so we match that now instead of waiting. The implementation stays ours: Kaan wants the systems to agree on endpoints and answers, not on code. If Team 16 later publishes and agrees to `mapping-v1.1.yaml`, reopen the `config_version` and DOCUMENTATION questions then.

**2026-10-18, revised again (TT-Q13).** Same answers for any path, not only the fixture: the rules now list every pattern of Team 16's mapping, read off Team 16's `doctracker/system/classify.py`, `analysis.py` and `mapping-v1.yaml` at `0db21ca`.
