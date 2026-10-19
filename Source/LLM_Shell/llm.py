# asks the model which documentation the changed code has outdated, the only code that calls an LLM

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass

from pydantic import BaseModel

from GitHub_Connector.schemas import AnalysisError, Category, ErrorCode, Finding, IssueType
from GitHub_Connector.settings import get_settings

# names the variable the Gemini SDK reads, unprefixed so no DRIFTER_ setting ever holds the key
KEY = "GEMINI_API_KEY"

# marks every finding as waiting for a person, the tool never resolves one itself
PENDING = "PENDING_REVIEW"

# tells the model what it is looking at and what counts as drift, kept apart from the files themselves
INSTRUCTION = """\
You check whether a repository's documentation still describes its code.

You are given the files that one commit changed, each as its text before and
after the change, and the repository's documentation files as they stand after
it. You are not given the rest of the repository.

Report a documentation file only when the code shown contradicts something that
file states: a renamed or removed function it still describes, or a changed
signature, argument, default, return value, command, flag or behaviour that it
still documents the old way. Name the changed file that contradicts it and say
what no longer matches.

Do not report a file because something is missing. Most of the repository's code
is not shown to you, so a documentation file describing code you cannot see is
not evidence of anything. Do not report wording, style, formatting, or anything
you cannot tie to the code shown.

Report nothing when no documentation contradicts the changes. An empty list is
the common and correct answer.
"""


@dataclass(frozen=True)
class CodeFile:
    # carries one changed code file as both its sides, a side is None where the file is absent there
    path: str
    category: Category
    base: str | None
    head: str | None


@dataclass(frozen=True)
class DocFile:
    # carries one documentation file as it stands at head
    path: str
    text: str


class _Drift(BaseModel):
    # holds one finding as the model returns it, the id and the status are added here, not there
    code_file: str
    documentation_file: str
    explanation: str


class _Drifts(BaseModel):
    # wraps the list, because a response schema needs one object at its root
    findings: list[_Drift]


def check(
    code: list[CodeFile], docs: list[DocFile], deadline: float | None = None, omitted: int = 0
) -> list[Finding]:
    # returns one finding per outdated doc, empty when there is nothing to compare or nothing drifted
    if not code or not docs:
        return []
    categories = {c.path: c.category for c in code}
    known_docs = {d.path for d in docs}
    return [
        Finding(
            finding_id="f-" + uuid.uuid4().hex,
            issue_type=IssueType.OUTDATED_DOCUMENTATION.value,
            code_file=drift.code_file,
            documentation_file=drift.documentation_file,
            change_category=categories[drift.code_file],
            explanation=drift.explanation,
            verification_status=PENDING,
        )
        for drift in _ask(_prompt(code, docs, omitted), deadline)
        # drops a finding naming a file we never sent, so every finding points at a real pair
        if drift.code_file in categories and drift.documentation_file in known_docs
    ]


def _ask(prompt: str, deadline: float | None) -> list[_Drift]:
    # makes the one call, every failure becomes LLM_UNAVAILABLE so an unchecked run is never a SUCCESS
    if not os.environ.get(KEY):
        raise _unavailable(f"{KEY} is not set")
    remaining = None if deadline is None else deadline - time.monotonic()
    if remaining is not None and remaining <= 0:
        raise _unavailable("the analysis deadline passed before the drift check")
    try:
        # imports here so the app starts, and the tests run, on a machine without the SDK installed
        from google import genai
        from google.genai import types

        # gives the call what is left of the analysis deadline, the SDK counts in milliseconds
        retries = types.HttpRetryOptions(attempts=0)
        options = types.HttpOptions(
            timeout=None if remaining is None else max(1, int(remaining * 1000)),
            retry_options=retries,
        )
        # holds the client in a name, the SDK closes its transport when the object is collected
        with genai.Client(http_options=options) as client:
            # restores zero retries, the pinned SDK changes it to one during client construction
            retries.attempts = 0
            interaction = client.interactions.create(
                model=get_settings().llm_model,
                input=prompt,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": _Drifts.model_json_schema(),
                },
                stream=False,
            )
            text = getattr(interaction, "output_text", None)
            if not isinstance(text, str):
                raise ValueError("the drift check returned no text")
            return _Drifts.model_validate_json(text).findings
    except Exception as exc:
        # covers the SDK, the network and a reply that isn't the schema, one failure as far as a caller sees
        raise _unavailable(f"the drift check did not complete: {exc}") from exc


def _unavailable(message: str) -> AnalysisError:
    # words the one failure the contract has for the drift check
    return AnalysisError(ErrorCode.LLM_UNAVAILABLE, message)


def _prompt(code: list[CodeFile], docs: list[DocFile], omitted: int = 0) -> str:
    # lays out the instruction, then each changed file as both sides, then the docs as they stand
    parts = [INSTRUCTION, "\n# Changed files\n"]
    for c in code:
        parts.append(f"\n## {c.path} ({c.category.value})\n")
        parts.append(_side("Before", c.base))
        parts.append(_side("After", c.head))
    parts.append("\n# Documentation, as it stands after the change\n")
    if omitted:
        files = "file" if omitted == 1 else "files"
        parts.append(f"\n{omitted} further documentation {files} were not included below.\n")
    for d in docs:
        parts.append(f"\n## {d.path}\n```\n{d.text}\n```\n")
    return "".join(parts)


def _side(label: str, text: str | None) -> str:
    # renders one side of a change, saying so plainly where the file does not exist on that side
    if text is None:
        return f"\n{label}: the file does not exist at this commit.\n"
    return f"\n{label}:\n```\n{text}\n```\n"
