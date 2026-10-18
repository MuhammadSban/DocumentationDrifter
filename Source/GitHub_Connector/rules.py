# gives each changed path a category from the ordered rules file, first match wins,
# and says which changed files are skipped, by name alone as Team 16's system does (TT-Q13)

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from fnmatch import fnmatchcase
from functools import lru_cache
from pathlib import Path

from GitHub_Connector.schemas import Category
from GitHub_Connector.settings import get_settings


@dataclass(frozen=True)
class _Rules:
    # holds one version of the rules file
    raw: bytes
    rules: list[tuple[str, Category]]
    fallback: Category
    supported_exts: frozenset[str]
    supported_names: frozenset[str]


def _rules(rules_file: Path) -> _Rules:
    # rereads the rules whenever the file changes on disk
    st = rules_file.stat()
    return _load(rules_file, st.st_mtime_ns, st.st_size)


@lru_cache(maxsize=8)
def _load(rules_file: Path, _mtime: int, _size: int) -> _Rules:
    # reads one version of the rules, line endings normalised so a Windows checkout hashes the same
    raw = rules_file.read_bytes().replace(b"\r\n", b"\n")
    data = json.loads(raw)
    rules = [(r["pattern"], Category(r["category"])) for r in data.get("rules", [])]
    exts = frozenset(ext.lower() for ext in data["supported_extensions"])
    return _Rules(raw, rules, Category(data["fallback"]), exts, frozenset(data["supported_filenames"]))


def config_version() -> str:
    # hashes the rules file, so any rule change shows up in every run file
    return hashlib.sha256(_rules(get_settings().rules_file).raw).hexdigest()[:12]


def classify(path: str) -> Category:
    # returns the category of the first rule that matches, else the fallback
    loaded = _rules(get_settings().rules_file)
    for pattern, category in loaded.rules:
        if matches(pattern, path):
            return category
    return loaded.fallback


def is_skipped(path: str) -> bool:
    # skips a file unless its extension, any case, or its exact name is on the supported lists
    loaded = _rules(get_settings().rules_file)
    name = path.rsplit("/", 1)[-1]
    dot = name.rfind(".")
    # reads an extension only after a leading character and before a trailing one, so .gitignore and a. have none
    ext = name[dot:].lower() if 0 < dot < len(name) - 1 else ""
    return ext not in loaded.supported_exts and name not in loaded.supported_names


def matches(pattern: str, path: str) -> bool:
    # matches one rule against a repo-relative path, gitignore style
    if "/" not in pattern:
        # matches a bare name pattern such as *.md against the file name, in any folder
        return fnmatchcase(path.rsplit("/", 1)[-1], pattern)
    if pattern.endswith("/**"):
        # matches a folder pattern such as docs/** against everything under it, from the root
        return path.startswith(pattern[:-2])
    return fnmatchcase(path, pattern)
