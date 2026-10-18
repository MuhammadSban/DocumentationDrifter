# covers cross-team tester ticket 06: a changed file is skipped by its name alone, as Team 16's system does (TT-Q13)

import json
from pathlib import Path

import pytest

PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 8
MB = 1024 * 1024
RULES = Path(__file__).resolve().parents[1] / "Source" / "GitHub_Connector" / "path_rules.json"


def analyse(api, head, **extra):
    # posts one analysis request and returns the parsed body
    r = api.post("/system/analyze", json={"repository": "octo/demo", "commit_id": head, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def paths(items):
    # lists the path of each entry
    return [i["path"] for i in items]


def test_skipped_file_is_still_reported_as_a_change(api, make_repo):
    repo = make_repo()
    repo.commit({"seed.txt": "0\n"})
    body = analyse(api, repo.commit({"logo.bin": b"\0\1\2", "notes.md": "hi\n"}))
    assert body["skipped"] == [{"path": "logo.bin", "reason": "UNSUPPORTED_FILE_TYPE"}]
    assert paths(body["changes"]) == ["logo.bin", "notes.md"]


@pytest.mark.parametrize(
    "name",
    ["a.py", "a.ipynb", "a.js", "a.ts", "a.java", "a.c", "a.h", "a.cpp", "a.hpp", "a.go", "a.rs", "a.rb", "a.sh", "a.sql",
     "a.md", "a.rst", "a.txt", "a.yaml", "a.yml", "a.json", "a.toml", "a.cfg", "a.ini", "a.csv",
     "NOTES.TXT", "Script.PY", "LICENSE", "Makefile", "Dockerfile", "README", "CODEOWNERS", "sub/dir/README"],
)
def test_a_supported_name_is_not_skipped(name):
    from GitHub_Connector import rules

    assert not rules.is_skipped(name)


@pytest.mark.parametrize(
    "name",
    ["a.png", "a.bin", "a.svg", "a.html", "a.xml", "a.pdf", "Pipfile.lock", "archive.tar.gz", "seed", "vendor/lib",
     "license", "makefile", "README.MD.bak", ".gitignore", "docs/.env", "a."],
)
def test_any_other_name_is_skipped(name):
    from GitHub_Connector import rules

    assert rules.is_skipped(name)


def test_content_never_decides_a_skip(api, make_repo):
    repo = make_repo()
    repo.commit({"seed.txt": "0\n"})
    head = repo.commit({
        "zero.txt": b"text" * 100 + b"\0" + b"more\n",
        "big.md": b"a" * (2 * MB),
        "latin1.txt": "café crème\n".encode("latin-1"),
        "text.png": "not an image\n",
    })
    body = analyse(api, head)
    assert body["skipped"] == [{"path": "text.png", "reason": "UNSUPPORTED_FILE_TYPE"}]
    assert paths(body["changes"]) == ["big.md", "latin1.txt", "text.png", "zero.txt"]


def test_deleted_and_renamed_files_are_skipped_by_their_reported_path(api, make_repo):
    repo = make_repo()
    repo.commit({"logo.png": PNG, "old.png": b"OLD" * 900, "keep.txt": "k\n"})
    body = analyse(api, repo.commit({"logo.png": None, "old.png": None, "new.png": b"OLD" * 900}))
    assert paths(body["skipped"]) == ["logo.png", "new.png"]
    assert [(c["path"], c["change_type"], c["old_path"]) for c in body["changes"]] == [
        ("logo.png", "DELETED", None),
        ("new.png", "RENAMED", "old.png"),
    ]


def test_unchanged_files_are_never_skipped(api, make_repo):
    repo = make_repo()
    repo.commit({"logo.png": PNG, "big.txt": b"a" * (2 * MB)})
    body = analyse(api, repo.commit({"readme.md": "changed\n"}))
    assert body["skipped"] == []
    assert paths(body["changes"]) == ["readme.md"]


def test_skipped_is_sorted_by_path(api, make_repo):
    repo = make_repo()
    repo.commit({"seed.txt": "0\n"})
    body = analyse(api, repo.commit({"z.png": PNG, "a.png": PNG, "m.bin": b"\0\1\2"}))
    assert paths(body["skipped"]) == ["a.png", "m.bin", "z.png"]


def test_the_supported_names_live_in_the_rules_file(api, make_repo, tmp_path, monkeypatch):
    from GitHub_Connector.settings import get_settings

    repo = make_repo()
    repo.commit({"seed.txt": "0\n"})
    head = repo.commit({"page.html": "<p>hi</p>\n"})
    before = analyse(api, head)
    assert before["skipped"] == [{"path": "page.html", "reason": "UNSUPPORTED_FILE_TYPE"}]

    data = json.loads(RULES.read_text())
    data["supported_extensions"].append(".html")
    edited = tmp_path / "rules.json"
    edited.write_text(json.dumps(data))
    monkeypatch.setenv("DRIFTER_RULES_FILE", str(edited))
    get_settings.cache_clear()

    after = analyse(api, head)
    assert after["skipped"] == []
    assert after["config_version"] != before["config_version"]


def test_no_file_is_ever_downloaded(api, make_repo):
    # removes both new blobs from the remote, so any attempt to download one fails the analysis
    from repos import git

    repo = make_repo()
    repo.commit({"seed.txt": "0\n"})
    head = repo.commit({"big.png": PNG, "notes.md": "hi\n"})
    for name in ("big.png", "notes.md"):
        blob = git("rev-parse", f"{head}:{name}", cwd=repo.bare)
        loose = repo.bare / "objects" / blob[:2] / blob[2:]
        assert loose.is_file(), f"expected {name} as a loose object"
        loose.chmod(0o644)  # git writes objects read-only, which Windows won't delete
        loose.unlink()
    body = analyse(api, head)
    assert body["skipped"] == [{"path": "big.png", "reason": "UNSUPPORTED_FILE_TYPE"}]
    assert paths(body["changes"]) == ["big.png", "notes.md"]
