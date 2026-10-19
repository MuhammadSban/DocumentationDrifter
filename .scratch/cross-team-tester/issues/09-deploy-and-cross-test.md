# 09: Deploy the tester, update the registry, cross-test both ways

**What to build:** The tester is live at `https://documentationdrifter-production.up.railway.app/tester`, the registry names it, and each team's tester has run once against the other's system, with the results ready for Phase 3, Q4.1 and Q6.1.

**Blocked by:** 01, 02, 03, 04, 05, 11

**Status:** ready-for-human · Kaan authorized committing and pushing `kaan_test`; Railway's source branch and the registry still need updating

**Spec:** docs/plan/decisions.md, TT-Q4 and TT-Q5; the course's "Register your services" and "Phase 3 cross-team check"

- [ ] `kaan_test` pushed and selected as Railway's deployment source, without merging to `main`; `GET /tester/openapi.json` answers after deployment.
- [ ] The registry row gives the tester base URL (`…/tester`, not `/system/test`) and the run notes from ticket 05.
- [ ] Our tester against Team 16's system: date, run/passed counts, coverage and the main problem recorded.
- [ ] Team 16's tester against our system: the same, recorded.
- [ ] Our tester against our own system: the same, for Q4.5.

## Comments

**2026-10-18, first cross-test (before deploying).** Our tester, run locally against Team 16's live system (`https://doc-tracker-5t4s.onrender.com/system`), session `078c75df-8d90-4294-b6e4-cc7ee648a63b`: T-01 to T-17 all pass, with code coverage 135/409, component 5/7 and system 5/10, matching Team 16's own tester on their system (session `3522571d-d30f-4ea0-b6fa-466223a15a90`, 17 pass and 6 skip). The other direction waits for ticket 11: no analysis on our deployed system answered that evening.
