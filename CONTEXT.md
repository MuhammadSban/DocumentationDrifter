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

## Cross-team testing

**System**:
A team's deployed project service, under `/system`: the pod's project API plus the two test routes the tester calls.
_Avoid_: backend, server (when the graded service is meant)

**Tester**:
A team's deployed test service, under `/tester`, that runs the shared test list against any system it is pointed at and returns a suite report.
_Avoid_: test runner (for the system's own test routes), the suite (when the service is meant)

**Test session**:
One run of the shared test list against one system, named by an id the tester makes and the system's setup accepts. A new run always needs a new session.
_Avoid_: run (that is an analysis's run file), job

**Shared test list**:
The pod's T-01 to T-23, each with its request against the fixture repo and its expected answer, run by both teams' testers so their reports line up.
_Avoid_: our tests, their tests, test plan

**Fixture repo**:
The pod's public test repository, `ParthGupta06/doc-tracker-fixtures`, whose commits the shared test list analyses.
_Avoid_: test repo (ours, `DocumentationDrifter-testrepo`, is an internal regression set)

**Mapping file**:
The pod's shared classification rules, `mapping-v1.1.yaml`, loaded by both systems; its version is the `config_version` of every result.
_Avoid_: path rules (our current local file), config

**Suite report**:
The tester's one answer for a test session: an outcome for every test on the shared test list, plus code, component and system coverage.
_Avoid_: test report (the system's own coverage answer), results

**Component**:
One of the pod's seven parts, C1 to C7: the web-service interface, repository fetch, change detection and classification, the mapping detector, result building and persistence, saved-result retrieval, and the review workflow. Counted as covered when an executed test exercises it.
_Avoid_: module, layer

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
The kind of file a change touches, chosen by the first matching rule in our `path_rules.json`, which gives the same answers as Team 16's mapping: REQUIREMENT, SPECIFICATION, ARCHITECTURE, DESIGN, IMPLEMENTATION or OTHER, in that order of precedence. There is no DOCUMENTATION category, so a doc file is OTHER unless a rule names it: the design-side folders (`requirements/`, `spec/`, `specs/`, `docs/requirements/`, `docs/spec/`, `docs/specs/`, `docs/architecture/`, `docs/design/`, `docs/adr/`), or a name such as `REQUIREMENTS*.md`, `ARCHITECTURE*.md` or `DESIGN*.md` in any folder (TT-Q12, TT-Q13; the full list is in `docs/spec.md`, section 3).
_Avoid_: change category (in prose), file type

**Skipped file**:
A changed path whose name has no supported extension or file name (decided by name alone, as Team 16's system does). It is listed in `skipped[]` with the reason `UNSUPPORTED_FILE_TYPE`, and is still reported as a change.
_Avoid_: unparsed, failed file

**Doc budget** (from v1.2):
The most documentation text sent to the LLM in one analysis (200 KB, set in config); docs past it are omitted from the prompt and counted there, without adding skipped files to the result.
_Avoid_: doc limit, context cap

## Findings (from v1.2)

**Finding**:
A doc file the LLM judges outdated because it contradicts the changed code, waiting for human review. Missing documentation is deferred until authored mappings are available.
_Avoid_: issue, warning, alert

**Mapping**:
The authored links that say which doc file describes which code. Added in v1.3 or v2; v1.1 and v1.2 have none.
_Avoid_: config, links file
