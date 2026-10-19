# 04: Component and system coverage in the suite report

**What to build:** Each test on the shared test list is tagged with the components and acceptance criteria it exercises, and the suite report counts them (TT-Q3, TT-Q7 row 8). Component coverage: `total` 7 (C1 to C7), `covered` the components exercised by at least one executed test. System coverage: `total` 10 (AC-01 to AC-10), counted the same way. Each `basis` names the list and the covered IDs, as Team 16's tester does ("Components C1-C7 listed in the pod specification exercised by at least one executed test: C1, C2, …"). A skipped test covers nothing.

**Blocked by:** 01

**Status:** ready-for-human · implemented (2026-10-18), not yet deployed. Each shared test is a `SharedTest` in `Source/Tester/suite.py` with its component and criteria tags; T-01 to T-07 take theirs from `expected_changes.json`. Any outcome but `skip` counts as executed, so a failing or erroring test still covers its tags. The tags are ours, chosen to give Team 16's numbers (5/7 and 5/10); Team 16's own per-test tags weren't available to copy. T-06 carries the same tags as T-01. Decided on 2026-10-18 (TT-Q3).

**Spec:** docs/plan/decisions.md, TT-Q3 and TT-Q7 row 8; CONTEXT.md, "Component"

- [x] Every test carries its component and AC tags in the same data that defines it.
- [x] `coverage.component` and `coverage.system` have `covered` ≤ `total` and a non-empty `basis` listing the covered IDs.
- [x] With T-01 to T-17 executed and T-18 to T-23 skipped, the numbers equal Team 16's on their own system: component 5/7 (C1, C2, C3, C5, C6), system 5/10 (AC-01, AC-06, AC-07, AC-08, AC-10).
- [x] `docs/spec.md` lists C1 to C7 with their names and phases, and says what exercising each one means.
- [x] The whole suite is green offline.

## Comments

**2026-10-18, TT-Q12.** The tags are now Team 16's own, read from their suite: T-14 is C1 and C6, and T-15 carries AC-06 and AC-08. The totals stay 5/7 and 5/10, and `basis` now reads word for word as theirs.
