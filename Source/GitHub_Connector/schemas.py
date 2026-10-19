# declares the v1 API contract, copied field for field from the reference service

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class Category(str, Enum):
    # names the kind of file a change touches, exactly Team 16's six (TT-Q12)
    IMPLEMENTATION = "IMPLEMENTATION"
    DESIGN = "DESIGN"
    ARCHITECTURE = "ARCHITECTURE"
    SPECIFICATION = "SPECIFICATION"
    REQUIREMENT = "REQUIREMENT"
    OTHER = "OTHER"


class ChangeType(str, Enum):
    # mirrors git's status letters, v1 never emits COPIED
    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"
    RENAMED = "RENAMED"
    COPIED = "COPIED"
    TYPE_CHANGED = "TYPE_CHANGED"


class Status(str, Enum):
    # marks a run's outcome, ERROR only for a saved run stopped by CHANGE_LIMIT_EXCEEDED
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


class ErrorCode(str, Enum):
    # lists the contract's failure codes, LLM_UNAVAILABLE joins in v1.2
    INVALID_REQUEST = "INVALID_REQUEST"
    REPOSITORY_NOT_FOUND = "REPOSITORY_NOT_FOUND"
    COMMIT_NOT_FOUND = "COMMIT_NOT_FOUND"
    TIMEOUT = "TIMEOUT"
    WRITE_FAILED = "WRITE_FAILED"


class AnalysisRequest(BaseModel):
    # carries one analysis ask, formats are checked by analyze() before any git work
    repository: str
    commit_id: str
    base_commit: str | None = None


class Change(BaseModel):
    # describes one changed path, old_path is set only for RENAMED
    path: str
    old_path: str | None = None
    change_type: ChangeType
    category: Category


class Skipped(BaseModel):
    # lists a changed path that could not be checked, with why
    path: str
    reason: str


class Finding(BaseModel):
    # flags one doc file for human review, empty in v1.1 and filled by the LLM in v1.2
    finding_id: str
    issue_type: str
    code_file: str
    documentation_file: str | None
    change_category: Category
    explanation: str
    verification_status: str


class ErrorBody(BaseModel):
    # answers every failed request, and names why a saved ERROR run stopped; code is a plain string, as theirs is
    code: str
    message: str


class AnalysisResult(BaseModel):
    # holds one run, SUCCESS or a saved ERROR, saved once and served back byte for byte
    analysis_id: str
    repository: str
    head_commit: str
    base_commit: str | None
    config_version: str
    tool_version: str
    status: Status
    error: ErrorBody | None
    issues: list[Finding]
    changes: list[Change]
    skipped: list[Skipped]
    created_at: str


class AnalysisError(Exception):
    # signals a failed analysis, the route maps code to an HTTP status

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def body(self) -> ErrorBody:
        # renders the error as the contract's ErrorBody
        return ErrorBody(code=self.code.value, message=self.message)
