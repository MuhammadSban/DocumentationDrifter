# 03: Shared tests T-01 to T-07: change detection on the fixture repo

**What to build:** The tester runs T-01 to T-07 against the tagged commits of `ParthGupta06/doc-tracker-fixtures`, comparing `changes[]` with the expected list as an unordered set of (path, old_path, change_type, category) (TT-Q9). Expected categories follow the mapping-v1.1 table (TT-Q7 row 6); docs/model.md and README.md are DOCUMENTATION. Expected answers live in one data file in the tester, so they can be handed to Team 16 and rechecked when `mapping-v1.1.yaml` is published.

Read from the fixture repo on 2026-10-18:

| Test | Commit (tag) | Expected changes |
|---|---|---|
| T-01 | c1-impl-only `add930c8` | `src/model.py` MODIFIED IMPLEMENTATION |
| T-02 | c2-add-mod-del `332e59e3` | `docs/model.md` MODIFIED DOCUMENTATION, `src/eval.py` ADDED IMPLEMENTATION, `src/train.py` DELETED IMPLEMENTATION |
| T-03 | c3-rename `9b03117f` | `src/evaluate.py` RENAMED from `src/eval.py`, IMPLEMENTATION |
| T-04 | c4-categories `55e4b15b` | `docs/architecture/overview.md` ARCHITECTURE, `docs/design/decisions.md` DESIGN, `requirements/REQUIREMENTS.md` REQUIREMENT, `specs/api.yaml` SPECIFICATION, all MODIFIED |
| T-05 | c6-binary `8adab1b1` | `assets/logo.png` MODIFIED and `data/weights.bin` ADDED, both OTHER and both in `skipped[]` as `UNSUPPORTED_FILE_TYPE` |
| T-06 | explicit `base_commit` across several commits | 4 changes; which base and head Team 16's tester uses is still to confirm |
| T-07 | c0-initial `d19092e1`, a root commit | `base_commit: null` and all 11 files ADDED |

**Blocked by:** 01

**Status:** ready-for-human · implemented (2026-10-18), not yet deployed; realigned to Team 16's suite the same evening (TT-Q12, see Comments). T-01 to T-07 are built from `Source/Tester/expected_changes.json`: the fixture commits by tag, as in Team 16's `commits.json`, and their expected answers. Our own system passes T-01, T-03 and T-07; T-02 and T-06 fail on DOCUMENTATION for `docs/model.md`, T-04 on the design-side categories (ticket 07) and T-05 on `BINARY_FILE` (ticket 06). Decided on 2026-10-18 (TT-Q8, TT-Q11, TT-Q12).

**Spec:** docs/plan/decisions.md, TT-Q7 to TT-Q11; Team 16's "Pod 15/16 Contract v1.1 Proposal", proposal 6

- [x] The expected answers for T-01 to T-07 sit in one data file, with each commit's full SHA and tag.
- [x] Each test passes, fails or errors with a message naming the expected and received sets.
- [x] T-05 checks the two skipped paths and their reason; T-07 checks `base_commit` is null and every change is ADDED.
- [x] T-06 uses the base and head Team 16 confirms, recorded in a comment on this ticket.
- [x] Against a stub target returning the expected answers every test passes, and a stub swapping one category fails exactly that test.
- [x] The whole suite is green offline.

## Comments

**2026-10-18, T-06's commits.** Nothing waits on Team 16: Phase 2 §4.2 and §5.3 ask only for fixed repos with manually defined expected results, so we define T-06 ourselves (Kaan). T-06 analyses head `c2-add-mod-del` (`332e59e3ba2b1a6c1a454ee75c3a71dfea0b4ff6`) with `base_commit` `c0-initial` (`d19092e138ea3f9788a8eac76005ee53d22940da`), two commits apart, and expects 4 changes: `docs/model.md` MODIFIED DOCUMENTATION, `src/eval.py` ADDED IMPLEMENTATION, `src/model.py` MODIFIED IMPLEMENTATION and `src/train.py` DELETED IMPLEMENTATION, with `base_commit` returned as sent. Of the four fixture pairs that span several commits with 4 changes (c0 to c2, c0 to c3, c4 to c6, c5 to c7), this one has no binary files, so it doesn't overlap T-05, and without the base its head gives T-02's three changes, so a system that ignores `base_commit` fails it. To hand to Team 16 with the data file.

**2026-10-18, TT-Q12, replaces the comment above.** Team 16 agrees only to what their suite checks, and their tester's source is public. T-06 is now theirs: head `c3-rename` with `base_commit` `c0-initial`, expecting `docs/model.md` MODIFIED OTHER, `src/evaluate.py` ADDED, `src/model.py` MODIFIED and `src/train.py` DELETED, all IMPLEMENTATION, and the base returned as sent. Doc files are OTHER in every expected answer, not DOCUMENTATION. T-01 also checks the default base is the first parent, and T-07 checks only the null base, 11 changes and all ADDED, not categories. Our own system passes T-01, T-03 and T-07; T-02 and T-06 fail on DOCUMENTATION, T-04 on the design-side categories, T-05 on `BINARY_FILE`.
