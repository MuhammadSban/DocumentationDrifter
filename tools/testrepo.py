# builds the public test repo deterministically, same SHAs on any machine: python tools/testrepo.py <folder>

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

AUTHOR = "DocumentationDrifter Fixtures <fixtures@documentation-drifter.invalid>"
# names the public copy on GitHub, published 2026-10-17 (ticket 11); republish it after any change to the labels
PUBLIC_REPO = "kaan-kanadasi/DocumentationDrifter-testrepo"
EPOCH = 1767225600  # starts at 2026-01-01T00:00:00Z, one minute per commit
MB = 1024 * 1024

TEXT = "".join(f"Line {i}: documentation drifter fixture text, kept long enough to rename well.\n" for i in range(30))
PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 4
LATIN1 = "Caf\xe9 cr\xe8me, not UTF-8\n".encode("latin-1")

# lists each step's files, as bytes, ("x", bytes), ("link", target), ("gitlink", sha) or None to delete
STEPS: list[tuple[str, dict]] = [
    ("root", {
        "README.md": "# Fixture repo\n",
        "src/app.py": "def main():\n    return 1\n",
        "docs/installation.rst": "Installation\n============\n\npip install fixture\n",
        "docs/old.md": TEXT,
        "requirements.txt": "requests==2.32.3\n",
        "Makefile": "all:\n\tpython src/app.py\n",
    }),
    ("modified", {"src/app.py": "def main():\n    return 2\n"}),
    ("added-and-deleted", {"src/util.py": TEXT, "Makefile": None}),
    ("renamed", {"src/util.py": None, "src/helpers.py": TEXT}),
    ("docs-category", {"docs/installation.rst": "Installation\n============\n\npip install fixture==2\n"}),
    ("hidden-paths", {
        ".gitignore": "*.pyc\n",
        ".github/workflows/ci.yml": "on: push\n",
        ".github/CONTRIBUTING.md": TEXT.replace("Line", "Contributing line"),
        "docs/.drafts/note.md": "draft\n",
        "lib/visible.py": "VISIBLE = True\n",
    }),
    ("renames-across-hidden", {
        ".github/CONTRIBUTING.md": None,
        "docs/contributing.md": TEXT.replace("Line", "Contributing line"),
        "docs/old.md": None,
        ".archive/old.md": TEXT,
    }),
    ("symlink", {"link-to-readme": ("link", "README.md"), "notes.txt": "notes\n", "switchy.txt": "regular\n"}),
    ("file-to-symlink", {"switchy.txt": ("link", "README.md")}),
    ("symlink-to-file", {"switchy.txt": "regular again\n"}),
    ("submodule", {"vendor/lib": ("gitlink", "1" * 40), "vendor/README.md": "vendored\n"}),
    ("binary", {"assets/logo.png": PNG}),
    ("oversize", {"data/big.csv": b"a" * MB + b"\n"}),
    ("non-utf8", {"docs/latin1.txt": LATIN1}),
    ("requirements-file", {"requirements-dev.txt": "pytest\n", "docs/requirements.txt": "sphinx\n"}),
    ("lockfile", {"poetry.lock": "# lock\n", "package-lock.json": "{}\n"}),
    ("many-files", {f"bulk/f{i:03d}.txt": f"{i}\n" for i in range(301)}),
    ("mixed", {
        "src/app.py": "def main():\n    return 3\n",
        "docs/guide.md": "# Guide\n",
        "requirements-dev.txt": None,
        "lib/visible.py": None,
        "lib/shown.py": "VISIBLE = True\n",
        ".env.example": "KEY=\n",
        ".assets/secret.png": PNG,
        "mixlink": ("link", "src/app.py"),
        "assets/icon.png": PNG,
        "vendor/other": ("gitlink", "2" * 40),
        "misc/latin.txt": LATIN1,
        "data/huge.txt": b"b" * (MB + 10),
        "run.sh": ("x", b"#!/bin/sh\necho run\n"),
    }),
    ("deleted", {"docs/guide.md": None}),
]


def change(path, change_type, category, old_path=None):
    # spells one expected change
    return {"path": path, "old_path": old_path, "change_type": change_type, "category": category}


def skip(path, reason):
    # spells one expected skipped file
    return {"path": path, "reason": reason}


# names the one skip reason, given by a file's name alone (TT-Q13)
UNSUPPORTED = "UNSUPPORTED_FILE_TYPE"

# maps each label to (head, base or None, changes, skipped), written by hand to check intent
EXPECTED = {
    "root": ("root", None, [
        change("Makefile", "ADDED", "OTHER"),
        change("README.md", "ADDED", "OTHER"),
        change("docs/installation.rst", "ADDED", "OTHER"),
        change("docs/old.md", "ADDED", "OTHER"),
        change("requirements.txt", "ADDED", "OTHER"),
        change("src/app.py", "ADDED", "IMPLEMENTATION"),
    ], []),
    "modified": ("modified", None, [change("src/app.py", "MODIFIED", "IMPLEMENTATION")], []),
    "added-and-deleted": ("added-and-deleted", None, [
        change("Makefile", "DELETED", "OTHER"),
        change("src/util.py", "ADDED", "IMPLEMENTATION"),
    ], []),
    "renamed": ("renamed", None, [change("src/helpers.py", "RENAMED", "IMPLEMENTATION", "src/util.py")], []),
    "docs-category": ("docs-category", None, [change("docs/installation.rst", "MODIFIED", "OTHER")], []),
    "hidden-paths": ("hidden-paths", None, [change("lib/visible.py", "ADDED", "IMPLEMENTATION")], []),
    "renames-across-hidden": ("renames-across-hidden", None, [
        change("docs/contributing.md", "ADDED", "OTHER"),
        change("docs/old.md", "DELETED", "OTHER"),
    ], []),
    "symlink": ("symlink", None, [
        change("link-to-readme", "ADDED", "OTHER"),
        change("notes.txt", "ADDED", "OTHER"),
        change("switchy.txt", "ADDED", "OTHER"),
    ], [skip("link-to-readme", UNSUPPORTED)]),
    "file-to-symlink": ("file-to-symlink", None, [change("switchy.txt", "TYPE_CHANGED", "OTHER")], []),
    "symlink-to-file": ("symlink-to-file", None, [change("switchy.txt", "TYPE_CHANGED", "OTHER")], []),
    "submodule": ("submodule", None, [
        change("vendor/README.md", "ADDED", "OTHER"),
        change("vendor/lib", "ADDED", "OTHER"),
    ], [skip("vendor/lib", UNSUPPORTED)]),
    "binary": ("binary", None, [change("assets/logo.png", "ADDED", "OTHER")], [skip("assets/logo.png", UNSUPPORTED)]),
    "oversize": ("oversize", None, [change("data/big.csv", "ADDED", "OTHER")], []),
    "non-utf8": ("non-utf8", None, [change("docs/latin1.txt", "ADDED", "OTHER")], []),
    "requirements-file": ("requirements-file", None, [
        change("docs/requirements.txt", "ADDED", "OTHER"),
        change("requirements-dev.txt", "ADDED", "OTHER"),
    ], []),
    "lockfile": ("lockfile", None, [
        change("package-lock.json", "ADDED", "OTHER"),
        change("poetry.lock", "ADDED", "OTHER"),
    ], [skip("poetry.lock", UNSUPPORTED)]),
    "many-files": ("many-files", None, [change(f"bulk/f{i:03d}.txt", "ADDED", "OTHER") for i in range(301)], []),
    "mixed": ("mixed", None, [
        change("assets/icon.png", "ADDED", "OTHER"),
        change("data/huge.txt", "ADDED", "OTHER"),
        change("docs/guide.md", "ADDED", "OTHER"),
        change("lib/shown.py", "RENAMED", "IMPLEMENTATION", "lib/visible.py"),
        change("misc/latin.txt", "ADDED", "OTHER"),
        change("mixlink", "ADDED", "OTHER"),
        change("requirements-dev.txt", "DELETED", "OTHER"),
        change("run.sh", "ADDED", "IMPLEMENTATION"),
        change("src/app.py", "MODIFIED", "IMPLEMENTATION"),
        change("vendor/other", "ADDED", "OTHER"),
    ], [
        skip("assets/icon.png", UNSUPPORTED),
        skip("mixlink", UNSUPPORTED),
        skip("vendor/other", UNSUPPORTED),
    ]),
    "deleted": ("deleted", None, [change("docs/guide.md", "DELETED", "OTHER")], []),
    "base-equals-head": ("docs-category", "docs-category", [], []),
    "explicit-base-range": ("renamed", "root", [
        change("Makefile", "DELETED", "OTHER"),
        change("src/app.py", "MODIFIED", "IMPLEMENTATION"),
        change("src/helpers.py", "ADDED", "IMPLEMENTATION"),
    ], []),
}

# names the tester cases each label stands for, "?" where M0 doesn't pin the case down
COVERS = {
    "modified": ["T-01?", "AC-01"],
    "added-and-deleted": ["T-02?", "AC-01"],
    "renamed": ["T-03"],
    "docs-category": ["T-04", "T-05"],
    "deleted": ["T-06?"],
    "mixed": ["T-07?", "AC-10"],
    "unknown-commit": ["AC-08"],
}


# names every label the manifest holds
LABELS = sorted([*EXPECTED, "short-sha", "unknown-commit"])


def _stream() -> bytes:
    # writes a fast-import stream for every step, one commit per step on main
    out = bytearray()
    for n, (name, files) in enumerate(STEPS):
        when = EPOCH + 60 * n
        message = f"{name}\n".encode()
        out += b"commit refs/heads/main\n"
        out += f"mark :{n + 1}\n".encode()
        out += f"author {AUTHOR} {when} +0000\ncommitter {AUTHOR} {when} +0000\n".encode()
        out += f"data {len(message)}\n".encode() + message
        if n:
            out += f"from :{n}\n".encode()
        for path in sorted(files):
            value = files[path]
            if value is None:
                out += f"D {path}\n".encode()
                continue
            if isinstance(value, tuple) and value[0] == "gitlink":
                out += f"M 160000 {value[1]} {path}\n".encode()
                continue
            mode, data = "100644", value
            if isinstance(value, tuple):
                mode = "120000" if value[0] == "link" else "100755"
                data = value[1]
            data = data.encode() if isinstance(data, str) else data
            out += f"M {mode} inline {path}\ndata {len(data)}\n".encode() + data + b"\n"
        out += b"\n"
    return bytes(out)


def _git(*args, cwd, data=None) -> str:
    # runs git with no user config, so nothing on the machine changes the result
    env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
    return subprocess.run(["git", *args], cwd=cwd, input=data, capture_output=True, check=True, env=env).stdout.decode().strip()


def build(dest: Path) -> dict:
    # writes the bare test repo into dest and returns its manifest
    dest.mkdir(parents=True, exist_ok=True)
    _git("init", "--quiet", "--bare", "--initial-branch=main", ".", cwd=dest)
    _git("config", "uploadpack.allowFilter", "true", cwd=dest)
    _git("config", "uploadpack.allowAnySHA1InWant", "true", cwd=dest)
    marks = dest / "fixture.marks"
    _git("fast-import", "--quiet", f"--export-marks={marks}", cwd=dest, data=_stream())
    sha_of_mark = dict(line.split(" ") for line in marks.read_text().split("\n") if line)
    marks.unlink()
    sha = {name: sha_of_mark[f":{n + 1}"] for n, (name, _) in enumerate(STEPS)}
    for name, value in sha.items():
        _git("tag", f"label/{name}", value, cwd=dest)

    labels = {}
    for label, (head, base, changes, skipped) in EXPECTED.items():
        names = [s for s, _ in STEPS]
        parent = sha[names[names.index(head) - 1]] if names.index(head) else None
        request = {"commit_id": sha[head]}
        if base is not None:
            request["base_commit"] = sha[base]
        labels[label] = {
            "request": request,
            "expect": {
                "status": 200,
                "head_commit": sha[head],
                "base_commit": sha[base] if base is not None else parent,
                "changes": changes,
                "skipped": skipped,
            },
            "covers": COVERS.get(label, []),
            "planted_drift": [],
        }
    labels["short-sha"] = {
        "request": {"commit_id": sha["modified"][:7]},
        "expect": {**labels["modified"]["expect"]},
        "covers": [],
        "planted_drift": [],
    }
    labels["unknown-commit"] = {
        "request": {"commit_id": "0" * 39 + "1"},
        "expect": {"status": 404, "code": "COMMIT_NOT_FOUND"},
        "covers": COVERS["unknown-commit"],
        "planted_drift": [],
    }
    manifest = {
        "format": 1,
        "about": "Labelled cases for DocumentationDrifter v1.1. Each label is one request and its expected answer; "
                 "planted_drift stays empty until v1.2 and v2 add drift cases.",
        "labels": dict(sorted(labels.items())),
    }

    # commits the manifest on top, since it has to name the SHAs before it
    body = (json.dumps(manifest, indent=2) + "\n").encode()
    last = len(STEPS)
    when = EPOCH + 60 * last
    stream = (
        f"commit refs/heads/main\nmark :{last + 1}\n"
        f"author {AUTHOR} {when} +0000\ncommitter {AUTHOR} {when} +0000\n"
        f"data 9\nmanifest\nfrom {sha[STEPS[-1][0]]}\n"
        f"M 100644 inline manifest.json\ndata {len(body)}\n"
    ).encode() + body + b"\n\n"
    _git("fast-import", "--quiet", cwd=dest, data=stream)
    return manifest


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python tools/testrepo.py <folder>")
    result = build(Path(sys.argv[1]))
    print(f"built {len(result['labels'])} labels into {sys.argv[1]}")
