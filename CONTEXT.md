# DocumentationDrifter

A service that looks at what changed between two commits of a public GitHub repo and flags documentation that may now be missing or outdated, for a human to review.

## Where the project is heading

**Product vision**:
The finished system that the Phase 2 specification describes, kept in [docs/vision/](docs/vision/README.md) as text plus its six diagrams. Each version takes inspiration from it but may differ from it; the roadmap says which version builds which part.
_Avoid_: the spec (when only the product vision is meant), final version (that is the last version we build, which may differ from the product vision), end product (its old name)

**Version**:
One iterative step towards the product vision, such as v1.1 or v2, with its scope in the roadmap.
_Avoid_: phase (the course's Phases 3 to 5 are deadlines, not versions)

## The other team

**Reference service**:
The pod's live v1 service, whose output ours must match apart from the known differences.
_Avoid_: their API, the pod (when the service is meant)

**Known difference**:
A named way our output may differ from the reference service's, agreed by Kaan and recorded in the decision log. It normally rests on an open question or a fault in the reference service.
_Avoid_: exception, allowed diff, deviation

## Requests and runs

**Analysis**:
One request to compare a head commit against a base commit in one repository, from validation to its final state.
_Avoid_: job, scan, check

**Run file**:
The JSON record of one successful analysis, written once and never edited.
_Avoid_: report, log, evidence file

**Head commit**:
The commit being analysed, given as `commit_id` and stored as a full 40-hex SHA.

**Base commit**:
The commit the head is compared against: `base_commit` if given, otherwise the head's first parent.
_Avoid_: parent (when the base was given explicitly)

**First audit**:
An analysis with no base commit, where every file counts as added. In v1 this happens only when the head is a root commit; a new-branch push sends the merge base with the default branch instead (decision 15, see the [decision log](docs/plan/decisions.md#decision-15-the-base-for-a-push-that-creates-a-branch-2026-10-17)).
_Avoid_: initial scan

## Parts of the service

**Connector**:
The code that reads the analysed repo with git: `fetch(repo, head, base)` returns a comparison, and it is the only code that runs git.
_Avoid_: GitHub connector for the whole `GitHub_Connector` folder, which also holds the API and the run store

**Run store**:
Where run files are saved and loaded by `analysis_id`: local disk in v1, a durable store from v3.
_Avoid_: store (alone), database

## Files

**Change**:
One changed path between base and head, with its change type and category.
_Avoid_: diff, delta

**Category**:
The kind of file a change touches, such as IMPLEMENTATION, DOCUMENTATION or OTHER, chosen by the first matching path rule.
_Avoid_: change category (in prose), file type

**Skipped file**:
A changed path that could not be checked, because its file type is unsupported, it is binary, too large or not UTF-8, or it is over the doc budget. It is listed in `skipped[]` with a reason code, and a changed one is still reported as a change.
_Avoid_: unparsed, failed file

**Doc budget** (from v1.2):
The most documentation text sent to the LLM in one analysis (200 KB, set in config); docs past it are skipped files.
_Avoid_: doc limit, context cap

## Findings (from v1.2)

**Finding**:
A doc file the LLM judges missing or outdated because of the changes, waiting for human review.
_Avoid_: issue, warning, alert

**Mapping**:
The authored links that say which doc file describes which code. Added in v1.3 or v2; v1.1 and v1.2 have none.
_Avoid_: config, links file
