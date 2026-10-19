# runs one analysis end to end, callable without HTTP by the API or a later Action

from __future__ import annotations

import re
import threading
import time
import uuid
from datetime import datetime, timezone

from GitHub_Connector import rules, runs
from GitHub_Connector.fetch import _deadline_passed, fetch
from GitHub_Connector.schemas import (
    AnalysisError,
    AnalysisRequest,
    AnalysisResult,
    Change,
    ErrorBody,
    ErrorCode,
    Skipped,
    Status,
)
from GitHub_Connector.settings import build_label, get_settings
from LLM_Shell import llm

# matches owner/name and 7-40 hex before any network call, \Z since $ would accept a trailing newline
REPOSITORY = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+\Z")
SHA = re.compile(r"^[0-9a-fA-F]{7,40}\Z")
# names the error of a saved ERROR run, not an HTTP failure, so it stays out of ErrorCode
CHANGE_LIMIT_EXCEEDED = "CHANGE_LIMIT_EXCEEDED"


def validate(request: AnalysisRequest) -> None:
    # rejects malformed input with INVALID_REQUEST, so garbage never reaches git
    def invalid(message: str) -> AnalysisError:
        return AnalysisError(ErrorCode.INVALID_REQUEST, message)

    if not REPOSITORY.match(request.repository):
        raise invalid("repository must use the format owner/name")
    if not SHA.match(request.commit_id):
        raise invalid("commit_id must be a 7-40 character hexadecimal commit SHA")
    if request.base_commit is not None and not SHA.match(request.base_commit):
        raise invalid("base_commit must be a 7-40 character hexadecimal commit SHA")


_slots_lock = threading.Lock()
_slots: tuple[int, threading.BoundedSemaphore] | None = None


def slot() -> threading.BoundedSemaphore:
    # hands out the shared semaphore that caps concurrent analyses at the configured limit
    global _slots
    limit = get_settings().max_concurrent
    with _slots_lock:
        if _slots is None or _slots[0] != limit:
            _slots = (limit, threading.BoundedSemaphore(limit))
        return _slots[1]


def analyze(request: AnalysisRequest) -> AnalysisResult:
    # bounds one analysis, including the wait for a free slot
    validate(request)
    deadline = time.monotonic() + get_settings().analysis_deadline
    semaphore = slot()
    if not semaphore.acquire(timeout=max(0, deadline - time.monotonic())):
        raise _deadline_passed()
    try:
        return _analyze(request, deadline)
    finally:
        semaphore.release()


def _analyze(request: AnalysisRequest, deadline: float) -> AnalysisResult:
    # compares head against base, classifies each change, saves the run file once
    with fetch(request.repository, request.commit_id, request.base_commit, deadline) as cmp:
        changes = [
            Change(
                path=c.path,
                old_path=c.old_path,
                change_type=c.change_type,
                category=rules.classify(c.path),
            )
            for c in cmp.changes
        ]
        skipped = [Skipped(path=s.path, reason=s.reason) for s in cmp.skipped]
        head, base = cmp.head, cmp.base

        # saves an over-limit run as ERROR with nothing listed and nothing asked, as Team 16's system does
        limit = get_settings().max_changed_files
        error, issues = None, []
        if len(changes) > limit:
            error = ErrorBody(
                code=CHANGE_LIMIT_EXCEEDED,
                message=f"{len(changes)} changed files exceeds the limit of {limit}",
            )
            changes, skipped = [], []
        else:
            code, docs, omitted = _inputs(cmp, changes, skipped)
            issues = llm.check(code, docs, deadline, omitted)

    result = AnalysisResult(
        analysis_id="an-" + uuid.uuid4().hex,
        repository=request.repository,
        head_commit=head,
        base_commit=base,
        config_version=rules.config_version(),
        tool_version=build_label(),
        status=Status.ERROR if error else Status.SUCCESS,
        error=error,
        issues=sorted(issues, key=lambda f: (f.documentation_file or "", f.code_file)),
        changes=sorted(changes, key=lambda c: c.path),
        skipped=sorted(skipped, key=lambda s: s.path),
        created_at=_now(),
    )
    try:
        runs.save(result.analysis_id, runs.dump(result))
    except OSError as exc:
        raise AnalysisError(ErrorCode.WRITE_FAILED, "The run file could not be saved") from exc
    return result


def _inputs(cmp, changes: list[Change], skipped: list[Skipped]) -> tuple[list, list, int]:
    # builds what the drift check reads: the changed code, the docs at head that fit the budget, and how many didn't
    done = {s.path for s in skipped}
    # leaves out the docs, they are sent whole at head, and anything skipped by name was never read
    wanted = [c for c in changes if not rules.is_doc(c.path) and c.path not in done]
    # reads the base side at old_path, or a rename would look like a file that never existed
    base = cmp.read_many([c.old_path or c.path for c in wanted], "base")
    head = cmp.read_many([c.path for c in wanted], "head")
    code = [
        llm.CodeFile(
            path=c.path,
            category=c.category,
            base=_text(base.get(c.old_path or c.path)),
            head=_text(head.get(c.path)),
        )
        for c in wanted
    ]

    # reads every candidate in one call, a size pass first would fetch each blob on its own
    candidate = [path for path in cmp.tree("head") if rules.is_doc(path) and not rules.is_skipped(path)]
    docs: list[llm.DocFile] = []
    omitted = 0
    budget, used = get_settings().doc_budget_bytes, 0
    for path, raw in cmp.read_many(candidate, "head").items():
        # drops a doc that is not readable text with no record, an untouched file was never ours to check
        text = None if b"\0" in raw[:8000] else _text(raw)
        if text is None:
            continue
        if used + len(raw) > budget:
            # counts a doc past the budget for the prompt, skipped[] stays Team 16's, by name alone
            omitted += 1
            continue
        used += len(raw)
        docs.append(llm.DocFile(path=path, text=text))
    return code, docs, omitted


def _text(raw: bytes | None) -> str | None:
    # decodes one file as UTF-8, None where it is absent or not text
    if raw is None:
        return None
    try:
        return raw.decode()
    except UnicodeDecodeError:
        return None


def _now() -> str:
    # formats the current time as ISO 8601 UTC with milliseconds and a Z
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
