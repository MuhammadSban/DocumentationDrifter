# 10: Answer Team 16's contract proposal and report their stuck session

**What to build:** Team 15's response on each row of Team 16's "Pod 15/16 Contract v1.1 Proposal", plus our row 9, and a note about their tester's stuck session, so both teams can record the agreement in Phase 3, Q3.2 and Q6.2.

**Blocked by:** None (can start immediately)

**Status:** ready-for-human · Kaan sends it

**Spec:** docs/plan/decisions.md, TT-Q7

- [ ] Rows 1, 2, 4, 5, 7 and 8 marked Agree. Rows 3 and 6 answered: for now we match their current contract (no DOCUMENTATION, doc files OTHER, `config_version` each team's own), and we'd agree to `mapping-v1.1.yaml` once it's published and in both test suites (TT-Q12).
- [ ] Row 9 proposed: both systems list hidden paths in `changes[]`.
- [ ] Told: our tester copies their suite's requests, expected answers and tags (`doctracker/tester` at `0db21ca`), and passed 17/17 against their system on 2026-10-18; asked them to tell us when their suite changes.
- [ ] Reported: their tester's session `7db7828e-a65c-4b03-87b7-2e05d780eafe` against our system (started about 16:50 on 2026-10-18) still answered 409 "the suite has not ended" after 20 minutes, where the course spec asks for the stored partial report after an abort.
- [ ] The agreement date and channel are added to TT-Q7 in the decision log.

## Comments

**2026-10-18, revised (TT-Q12).** Their tester's source is public, so the questions about T-06's commits and the fixture commit for T-14 to T-17 are answered: T-06 is `c3-rename` against `c0-initial`, and T-14, T-16 and T-17 analyse `c1-impl-only`, `c2-add-mod-del` and `c4-categories`. Row 6 can't be a plain Agree while Team 16's contract has no DOCUMENTATION, because that would make ours differ from theirs (ticket 07, revised).
