# Docs

Specs and documentation for DocumentationDrifter. The glossary is [CONTEXT.md](../CONTEXT.md) at the repo root, and the tickets being worked on live in `.scratch/`.

## Read in this order

New to the project? Start with the [v1.1 guide](Models/v1/v1.1/v1.1-guide.html), a plain-language overview of what v1.1 built, what v1.2 adds and how the GitHub Action comes in v3. GitHub shows an HTML file as source, so open it from a local clone.

1. [CONTEXT.md](../CONTEXT.md): the words the project uses.
   Then [spec.md](spec.md): the one current spec, what the service does and what counts as correct.
2. [plan/roadmap.md](plan/roadmap.md): the one plan, version by version (v1.1, v1.2, v2 and on).
3. The current version:
   - **v1.1 (built):** [Models/v1/v1.1/spec-v1.1.md](Models/v1/v1.1/spec-v1.1.md), with its tickets in `.scratch/v1-1-change-detection/`.
   - **v1.2 (implemented on `kaan_test`, awaiting deployment):** see the v1 section of the [roadmap](plan/roadmap.md).
4. [Models/v1/](Models/v1/README.md): the v1 models, M1 to M5, narrowed from the product vision's M1 to M5.
5. [plan/decisions.md](plan/decisions.md): every decision with its reason.

## Find it by question

| Question | Where |
|---|---|
| What does a word mean? | [CONTEXT.md](../CONTEXT.md) |
| What gets built in which version? | [plan/roadmap.md](plan/roadmap.md) |
| What must the service do now, and what counts as correct? | [spec.md](spec.md) |
| What exactly must v1.1 do? | [Models/v1/v1.1/spec-v1.1.md](Models/v1/v1.1/spec-v1.1.md) |
| Why was something decided? | [plan/decisions.md](plan/decisions.md), and the decisions table at the end of the roadmap |
| What are the exact rules the code must match? | [Models/v1/](Models/v1/README.md), M1 to M5 |
| Which file holds a model's box? | "From boxes to files" in [Models/v1/README.md](Models/v1/README.md) |
| Why does the system exist at all? | [vision/README.md](vision/README.md) |
| What is the next ticket? | `.scratch/v1-1-change-detection/to_do.md` |

## What each folder holds

| Folder | What it holds | Status |
|---|---|---|
| [vision/](vision/README.md) | The product vision: the Phase 2 specification as text, its six diagrams and schema v14 | Inspiration, not a blueprint |
| [plan/](plan/roadmap.md) | The roadmap and the decision log | **Current.** Where these disagree with the product vision, they win. |
| [plan/reports/](plan/reports/) | One-off reports: Actions readiness, the report to the pod, the MAGE research notes | Dated snapshots, not updated |
| [plan/history/](plan/history/) | The early build guides: the product vision plan, the M0 build order, the commit fetcher plan, the connector steps | **Superseded** by the roadmap and the v1.1 spec, kept for their reasoning |
| [Models/](Models/v1/README.md) | The models and specs of each version (v1 so far, with the v1.1 spec in `v1/v1.1/`) and the v1.1 guide. Agents working on one area are meant to read the shared models plus the ones for that area. | Current |
| [agents/](agents/) | How the agent skills use this repo: issue tracker, triage labels, domain docs | Current |

## Where a new doc goes

- A decision: a new dated section at the end of `plan/decisions.md`.
- A version's spec: `Models/<major>/<version>/spec-<version>.md` (v1.2's goes in `Models/v1/v1.2/`).
- A model of what a version builds: `Models/<major>/<major>_models/` (today `Models/v1/v1_models/`).
- A one-off investigation: `plan/reports/`, dated in its first line.
- A plan that a newer one replaces: move it to `plan/history/` and add the "History, superseded" banner at its top.
- Then add it to the tables above, so this page stays the one way in.
