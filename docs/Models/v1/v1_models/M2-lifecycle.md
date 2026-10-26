# M2 · Analysis lifecycle

**Question:** What can happen to one analysis request, and how does each path end?

```mermaid
stateDiagram-v2
  accTitle: M2 analysis lifecycle
  accDescr: These are the states of one request, mostly inside analyze(). A request is validated, its commits are resolved, its changes are analysed, and the run file is saved. Invalid input ends in 400, a missing repo or commit in 404, and a git timeout, the overall deadline, a failed LLM call (v1.2) or a write failure in 500. Only the success path saves a run file. At most two analyses run at once.

  [*] --> VALIDATING: POST /system/analyze · at most 2 at once
  VALIDATING --> REJECTED: field missing or malformed
  VALIDATING --> RESOLVING: valid, slot free
  VALIDATING --> FAILED: no slot free within 120 s
  RESOLVING --> NOT_FOUND: repo missing or private, or SHA unknown
  RESOLVING --> ANALYZING: head and base resolved
  RESOLVING --> FAILED: git timeout or overall deadline
  ANALYZING --> SAVING: changes[] and skipped[] sorted
  ANALYZING --> FAILED: git timeout or overall deadline
  ANALYZING --> FAILED: LLM call fails (v1.2)
  ANALYZING --> FAILED: unforeseen error
  SAVING --> SUCCESS: run file written
  SAVING --> FAILED: write fails

  VALIDATING: VALIDATING · REQ-05
  RESOLVING: RESOLVING · REQ-06 · anonymous clone, rev-parse head, base or first parent
  ANALYZING: ANALYZING · REQ-01 · git diff -M, file rules (M3) · v1.2 adds the LLM drift check (REQ-02)
  SAVING: SAVING · REQ-04 · assign analysis_id, write runs/id.json
  SUCCESS: SUCCESS · 200, status SUCCESS, error null
  REJECTED: REJECTED · 400 INVALID_REQUEST, nothing saved
  NOT_FOUND: NOT_FOUND · 404 REPOSITORY_NOT_FOUND or COMMIT_NOT_FOUND, nothing saved
  FAILED: FAILED · 500 TIMEOUT, LLM_UNAVAILABLE (v1.2), WRITE_FAILED or INTERNAL_ERROR, nothing saved

  SUCCESS --> [*]
  REJECTED --> [*]
  NOT_FOUND --> [*]
  FAILED --> [*]
```

These are the states of one request. The route rejects a missing field before `analyze()` runs, and every other state belongs to `analyze()`. The route maps each final state to its status code, so a later caller of `analyze()` gets the same outcomes. The lifecycle stays synchronous: a QUEUED state would break the pod contract.

- **Representation.** Four working states and four final states. Each final state names its HTTP status and error code. Two guards bound the load: a 120 s deadline per analysis (60 s per git call), which ends in 500 `TIMEOUT`, and at most two analyses at once, with extra requests waiting up to 120 s for a slot and then ending in 500 `TIMEOUT`. All four values live in config. From v1.2, a failed LLM call (down, timeout, rate limit or missing key) ends in 500 `LLM_UNAVAILABLE`. Any error nothing foresaw, such as an unexpected git failure, ends in 500 `INTERNAL_ERROR` (2026-10-25).
- **Property.** A request that ends anywhere but SUCCESS returns an `ErrorBody` and saves nothing, so a failed check is never reported as successful (REQ-05). The temporary clone is deleted when the `fetch()` block exits, success or not (REQ-06). `GET /system/analysis/{id}` returns a saved file byte for byte, or 404 when the id is unknown.
- **Checked by.** AC-07 and AC-08 (the 400 and 404 cases), connector test 6 (unknown SHA), AC-06 and T-05 (the saved file comes back unchanged), and a test that no temporary clone is left after an error.
