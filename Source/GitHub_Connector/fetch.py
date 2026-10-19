# reads the analysed repo with git, the only code in v1 that runs git

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from GitHub_Connector import rules
from GitHub_Connector.schemas import AnalysisError, ChangeType, ErrorCode
from GitHub_Connector.settings import get_settings

# maps git's status letters to the contract's change types
_STATUS = {
    "A": ChangeType.ADDED,
    "M": ChangeType.MODIFIED,
    "D": ChangeType.DELETED,
    "R": ChangeType.RENAMED,
    "T": ChangeType.TYPE_CHANGED,
}

# keeps plain and executable files, the only ones read as text
REGULAR = {"100644", "100755"}

# lists symlinks and submodules in changes[] and skips them unread, as the reference does (decision T12-Q10)
LINKS = {"120000", "160000"}

# names the one skip reason, as Team 16's system gives it (TT-Q13)
SKIP_UNSUPPORTED = "UNSUPPORTED_FILE_TYPE"

# caps how many paths one prefetch names, so a repo full of docs cannot overflow the argument list
WARM_PATHS = 500


@dataclass(frozen=True)
class FileChange:
    # describes one changed path as git reports it
    path: str
    change_type: ChangeType
    old_path: str | None = None


@dataclass(frozen=True)
class SkippedFile:
    # names a changed path that could not be checked, with a reason code
    path: str
    reason: str


@dataclass
class Comparison:
    # carries what changed between base and head, valid only inside fetch()
    repo: str
    head: str
    base: str | None
    _git: _Git
    changes: list[FileChange] = field(default_factory=list)
    skipped: list[SkippedFile] = field(default_factory=list)
    _empty: str | None = None

    def read(self, path: str, side: str) -> bytes | None:
        # returns a file's bytes at "base" or "head" from git objects, None where it is missing
        sha = self.head if side == "head" else self.base
        if sha is None:
            return None
        proc = self._git.run("cat-file", "blob", f"{sha}:{path}", check=False)
        return proc.stdout if proc.returncode == 0 else None

    def read_many(self, paths: list[str], side: str) -> dict[str, bytes]:
        # reads several files in one call, leaving out any that is absent or not a blob on this side
        sha = self.head if side == "head" else self.base
        if sha is None or not paths:
            return {}
        self._warm(sha, paths)
        proc = None
        if not any("\n" in path or "\r" in path for path in paths):
            revs = "".join(f"{sha}:{p}\n" for p in paths).encode("utf-8", "surrogateescape")
            proc = self._git.run("cat-file", "--batch", input=revs, check=False)
        if proc is None or proc.returncode != 0:
            # reads individually for line breaks or a batch that failed on an unfetchable submodule
            found = {}
            for path in paths:
                raw = self.read(path, side)
                if raw is not None:
                    found[path] = raw
            return found
        out, found, pos = proc.stdout, {}, 0
        for path in paths:
            end = out.index(b"\n", pos)
            header = out[pos:end].rsplit(b" ", 2)
            if len(header) != 3 or not header[2].isdigit():
                # an absent or ambiguous path prints one line and no content
                pos = end + 1
                continue
            start, size = end + 1, int(header[2])
            # keeps blobs only, as a gitlink resolves to a commit object that is not the file's text
            if header[1] == b"blob":
                found[path] = out[start:start + size]
            pos = start + size + 1
        return found

    def _warm(self, sha: str, paths: list[str]) -> None:
        # names the files in a diff, which fetches their blobs in one request as git diff already does;
        # reading them straight away makes a blobless clone fetch each blob on its own
        if self._empty is None:
            self._empty = self._git.out("hash-object", "-t", "tree", "--stdin")
        for start in range(0, len(paths), WARM_PATHS):
            batch = paths[start:start + WARM_PATHS]
            self._git.run("diff", "--numstat", self._empty, sha, "--", *batch, check=False)

    def tree(self, side: str) -> list[str]:
        # lists the kept files at "base" or "head", without -l so no blob is fetched
        sha = self.head if side == "head" else self.base
        if sha is None:
            return []
        raw = self._git.run("ls-tree", "-r", "-z", "--full-tree", sha).stdout
        paths = []
        for entry in raw.decode("utf-8", "surrogateescape").split("\0"):
            if entry:
                meta, path = entry.split("\t", 1)
                if kept(path, meta.split(" ")[0]):
                    paths.append(path)
        return sorted(paths)


class _Git:
    # runs git anonymously inside one temporary clone

    def __init__(self, workdir: Path, deadline: float | None = None) -> None:
        self.workdir = workdir
        self.deadline = deadline
        self.timeout = get_settings().git_timeout
        self.env = {
            **os.environ,
            "GIT_TERMINAL_PROMPT": "0",  # fails a private repo at once instead of asking
            "GIT_ASKPASS": "",
            "SSH_ASKPASS": "",
            "LC_ALL": "C",
        }

    def run(
        self, *args: str, cwd: Path | None = None, check: bool = True, input: bytes | None = None
    ) -> subprocess.CompletedProcess[bytes]:
        # runs one git command with no credential helper, returns raw bytes
        cmd = ["git", "-c", "credential.helper=", "-c", "core.quotepath=false", *args]
        limit, overall = self.timeout, False
        if self.deadline is not None:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise _deadline_passed()
            if remaining < limit:
                limit, overall = remaining, True
        proc = _run(cmd, cwd or self.workdir / "clone", self.env, input or b"", limit)
        if proc is None:
            if overall:
                raise _deadline_passed()
            raise AnalysisError(ErrorCode.TIMEOUT, f"A git call took longer than {self.timeout:g} s")
        if check and proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd, proc.stdout, proc.stderr)
        return proc

    def ok(self, *args: str) -> bool:
        # reports whether a git command succeeds, used for probes like rev-parse
        return self.run(*args, check=False).returncode == 0

    def out(self, *args: str) -> str:
        # runs a git command and returns its trimmed text output
        return self.run(*args).stdout.decode("utf-8", "surrogateescape").strip()


def _deadline_passed() -> AnalysisError:
    # words the overall deadline failure
    return AnalysisError(
        ErrorCode.TIMEOUT,
        f"The analysis took longer than {get_settings().analysis_deadline:g} s",
    )


def _run(
    cmd: list[str], cwd: Path, env: dict[str, str], data: bytes, limit: float
) -> subprocess.CompletedProcess[bytes] | None:
    # captures output in files, so an escaped helper cannot hold an output pipe open after timeout
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        proc: subprocess.Popen[bytes] = subprocess.Popen(
            cmd, cwd=cwd, env=env, stdin=subprocess.PIPE,
            stdout=out, stderr=err,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            start_new_session=sys.platform != "win32",
        )
        try:
            proc.communicate(data, timeout=limit)
        except subprocess.TimeoutExpired:
            _kill_group(proc)
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            return None
        out.seek(0)
        err.seek(0)
        return subprocess.CompletedProcess(cmd, proc.returncode, out.read(), err.read())


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    # stops git and every helper it started, such as upload-pack or index-pack
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1,
            )
        except subprocess.TimeoutExpired:
            pass
    else:
        import signal

        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    proc.kill()


def _remote_url(repo: str) -> str:
    # builds the clone URL, tests repoint the base at local bare repos
    base = get_settings().remote_base_url
    return base.rstrip("/") + "/" + repo + ".git"


def _rmtree(path: Path) -> None:
    # deletes a clone, clearing read-only bits that git sets on pack files (Windows)
    def _retry(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_retry)
    else:
        shutil.rmtree(path, onerror=_retry)


@contextmanager
def fetch(
    repo: str, head: str, base: str | None = None, deadline: float | None = None
) -> Iterator[Comparison]:
    # clones repo blobless and yields the comparison, git calls past deadline (monotonic) fail with TIMEOUT
    clone_root = get_settings().clone_dir
    if clone_root is not None:
        clone_root.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="drifter-", dir=clone_root))
    try:
        git = _Git(workdir, deadline)
        _clone(git, repo)
        head_sha = _resolve(git, head, repo)
        base_sha = _resolve(git, base, repo) if base is not None else _first_parent(git, head_sha)
        cmp = Comparison(repo=repo, head=head_sha, base=base_sha, _git=git)
        # compares a first audit against the empty tree, so every file counts as added
        old = base_sha if base_sha is not None else git.out("hash-object", "-t", "tree", "--stdin")
        cmp.changes = _diff(git, old, head_sha)
        cmp.skipped = _skipped(cmp.changes)
        yield cmp
    finally:
        _rmtree(workdir)


def _clone(git: _Git, repo: str) -> None:
    # makes a blobless, no-checkout clone, so nothing from the repo lands on disk as files
    proc = git.run(
        "clone", "--filter=blob:none", "--no-checkout", "--quiet",
        _remote_url(repo), str(git.workdir / "clone"),
        cwd=git.workdir, check=False,
    )
    if proc.returncode != 0:
        raise AnalysisError(
            ErrorCode.REPOSITORY_NOT_FOUND,
            f"repository {repo} was not found or is not public",
        )


def _resolve(git: _Git, sha: str, repo: str) -> str:
    # expands a SHA to its full 40-hex form, fetching a full SHA by id when no branch reaches it
    sha = sha.lower()
    full = len(sha) == 40
    if full and not _present(git, sha):
        # asks for the commit by id, GitHub serves any commit in the repo this way
        git.run("fetch", "--quiet", "--no-tags", "--filter=blob:none", "origin", sha, check=False)
    proc = git.run("rev-parse", "--verify", "--quiet", "--end-of-options", f"{sha}^{{commit}}", check=False)
    if proc.returncode != 0:
        if full:
            raise AnalysisError(ErrorCode.COMMIT_NOT_FOUND, f"commit {sha} was not found in {repo}")
        raise AnalysisError(
            ErrorCode.COMMIT_NOT_FOUND,
            f"Commit {sha} not found or ambiguous; a short SHA only works for a commit on a "
            "branch or tag, so send the full 40-character SHA",
        )
    return proc.stdout.decode().strip()


def _present(git: _Git, sha: str) -> bool:
    # checks the clone for an object without a lazy fetch (git 2.44+ honours the flag)
    git.env["GIT_NO_LAZY_FETCH"] = "1"
    try:
        return git.ok("cat-file", "-e", sha)
    finally:
        del git.env["GIT_NO_LAZY_FETCH"]


def _first_parent(git: _Git, head: str) -> str | None:
    # returns the head's first parent, None for a root commit
    proc = git.run("rev-parse", "--verify", "--quiet", f"{head}^1", check=False)
    return proc.stdout.decode().strip() if proc.returncode == 0 else None


def kept(path: str, mode: str) -> bool:
    # admits regular files, including dot-paths
    return mode in REGULAR


def listed(path: str, mode: str) -> bool:
    # admits changed files and links, including dot-paths
    return mode in REGULAR or mode in LINKS


def _diff(git: _Git, old: str, head: str) -> list[FileChange]:
    # lists changed paths between old and head, renames only, never copies
    raw = git.run("diff", "--raw", "-z", "-M", "--no-abbrev", "--no-ext-diff", old, head).stdout
    fields = raw.decode("utf-8", "surrogateescape").split("\0")
    changes: list[FileChange] = []
    i = 0
    while i < len(fields) and fields[i]:
        # reads ":oldmode newmode oldsha newsha status" then one or two paths
        old_mode, new_mode, _, _, status = fields[i][1:].split(" ")
        letter = status[0]
        if letter == "R":
            old_path, new_path = fields[i + 1], fields[i + 2]
            i += 3
            # checks each side's mode, preserving the rename when both are listed
            old_ok, new_ok = listed(old_path, old_mode), listed(new_path, new_mode)
            if old_ok and new_ok:
                changes.append(FileChange(new_path, ChangeType.RENAMED, old_path))
            elif new_ok:
                changes.append(FileChange(new_path, ChangeType.ADDED))
            elif old_ok:
                changes.append(FileChange(old_path, ChangeType.DELETED))
            continue
        path = fields[i + 1]
        i += 2
        # judges the head side, or the base side for a deletion
        if letter == "D":
            if listed(path, old_mode):
                changes.append(FileChange(path, ChangeType.DELETED))
        elif listed(path, new_mode):
            changes.append(FileChange(path, _STATUS[letter]))
    return changes


def _skipped(changes: list[FileChange]) -> list[SkippedFile]:
    # lists the changes whose names are outside the supported lists, never reading a file (TT-Q13)
    return [SkippedFile(c.path, SKIP_UNSUPPORTED) for c in changes if rules.is_skipped(c.path)]
