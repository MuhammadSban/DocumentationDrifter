# v2 models

What v2 builds beyond the [roadmap](../../plan/roadmap.md)'s v2 section, decided as it comes up. Each part says what is decided and what is still open.

## Push trigger: a GitHub Action calls the service on push

**Decided (Kaan, 2026-10-18):** the GitHub Action that the roadmap and decision 14 placed in v3 moves into v2.

### Why

A change pushed to `main` took about 4½ minutes to reach the service. The service and Railway were not the cause. Measured on 2026-10-18 with a one-line commit to this repo (`7777e71`):

| Time (UTC) | Event | Since the push |
|---|---|---|
| 16:43:38 | Commit pushed to `main` | 0 s |
| 16:44:03 | A direct `POST /system/analyze` answers correctly in 0.37 s | +25 s |
| 16:44:06 | Railway's redeploy is live, with no downtime | +28 s |
| 16:48:14 | The console's next poll finds the commit and the analysis takes 0.28 s | +4 min 36 s |

The wait is the console's 300 s poll of `api.github.com`. Polling faster doesn't scale: anonymous calls get 60 an hour per IP, and conditional requests (304) still count without a token (checked the same day). So one watched repo at 60 s already uses the whole budget.

### What it is

```
today: the console polls GitHub
  push ──► GitHub
              ▲  "any new commit?" every 300 s (60 calls/hr budget)
              │
          console in a browser ──► POST /system/analyze ──► Railway ──► run file
          wait: 0–300 s                                     0.3 s

v2: the push starts the analysis
  push ──► GitHub ──► Actions runner (starts in 2–4 s)
                         │ 1. GET  /system/health  (warm-up, with retries)
                         │ 2. POST /system/analyze {head: after, base: before}
                         ▼
                      Railway ──► run file
                         │
                         ▼
                      Action summary + run file as an artifact
```

The Action is a thin client of `POST /system/analyze`, so the contract doesn't change. It follows the design in the [actions readiness report](../../plan/reports/actions-readiness.md), with two facts updated: our repo is now public, so other repos can `uses:` a reusable workflow from it, and the service is on Railway, not Render.

**Expected time from push to result:** about 5–10 s, against 0–300 s today. This is estimated from this repo's last six Actions runs (job start 2–4 s after the event, setup 1–2 s) plus the 0.4 s analysis. A real workflow has not been measured yet.

## Open: how a run reaches the console

**Open, recommendation only (2026-10-18).** Once the Action starts runs, the console no longer finds them by polling GitHub, so the service has to tell it. There are two ways: the browser polls our server for a repo's runs, or the server pushes each new run to the open page with Server-Sent Events. Both need durable run storage (roadmap v3 item 1) and a route that lists a repo's runs (v3 item 5) brought into v2.

The recommendation is to poll every 5 s only while the console tab is visible, and to keep runs in a separate evidence repo rather than a Railway volume. The reasons, sources and what the vision diagrams say are in [poll or SSE](poll_or_sse.md).
