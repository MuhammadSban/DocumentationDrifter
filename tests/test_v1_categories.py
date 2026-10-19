# covers cross-team tester ticket 07: categories with the same answers as Team 16's system for any path (TT-Q13)

import json
from pathlib import Path

import pytest

RULES = Path(__file__).resolve().parents[1] / "Source" / "GitHub_Connector" / "path_rules.json"

# lists each rule's matches and near misses, as Team 16's mapping-v1.yaml answers them
CASES = {
    # REQUIREMENT: requirements/**, docs/requirements/**, **/REQUIREMENTS*.md
    "requirements/REQUIREMENTS.md": "REQUIREMENT",
    "requirements/deep/notes.txt": "REQUIREMENT",
    "docs/requirements/r1.md": "REQUIREMENT",
    "REQUIREMENTS.md": "REQUIREMENT",
    "pkg/sub/REQUIREMENTS-v2.md": "REQUIREMENT",
    "requirements.txt": "OTHER",
    "requirements-dev.txt": "OTHER",
    "docs/requirements.txt": "OTHER",
    "requirements.md": "OTHER",
    "REQUIREMENTS.txt": "OTHER",
    "requirements": "OTHER",
    # SPECIFICATION: spec/**, specs/**, docs/spec/**, docs/specs/**, **/openapi*.yaml, **/openapi*.yml, **/openapi*.json
    "spec/api.md": "SPECIFICATION",
    "specs/api.yaml": "SPECIFICATION",
    "docs/spec/x.md": "SPECIFICATION",
    "docs/specs/y/z.md": "SPECIFICATION",
    "openapi.yaml": "SPECIFICATION",
    "api/openapi-v2.yml": "SPECIFICATION",
    "a/b/openapi.json": "SPECIFICATION",
    "specification/a.md": "OTHER",
    "openapi.yaml.bak": "OTHER",
    "spec.md": "OTHER",
    "src/spec/a.md": "OTHER",
    # ARCHITECTURE: docs/architecture/**, **/ARCHITECTURE*.md, **/model_config.*
    "docs/architecture/overview.md": "ARCHITECTURE",
    "ARCHITECTURE.md": "ARCHITECTURE",
    "src/ARCHITECTURE-notes.md": "ARCHITECTURE",
    "model_config.json": "ARCHITECTURE",
    "configs/model_config.yaml": "ARCHITECTURE",
    "architecture.md": "OTHER",
    "model_config.d/x.txt": "OTHER",
    # DESIGN: docs/design/**, docs/adr/**, **/DESIGN*.md
    "docs/design/decisions.md": "DESIGN",
    "docs/adr/0001-record.md": "DESIGN",
    "DESIGN.md": "DESIGN",
    "lib/DESIGN_v2.md": "DESIGN",
    "docs/designs/x.md": "OTHER",
    "design.md": "OTHER",
    # IMPLEMENTATION: **/*.py, .ipynb, .js, .ts, .java, .c, .h, .cpp, .hpp, .go, .rs, .rb, .sh, .sql
    "setup.py": "IMPLEMENTATION",
    "src/model.py": "IMPLEMENTATION",
    "nb/a.ipynb": "IMPLEMENTATION",
    "web/app.js": "IMPLEMENTATION",
    "web/app.ts": "IMPLEMENTATION",
    "j/A.java": "IMPLEMENTATION",
    "c/a.c": "IMPLEMENTATION",
    "c/a.h": "IMPLEMENTATION",
    "c/a.cpp": "IMPLEMENTATION",
    "c/a.hpp": "IMPLEMENTATION",
    "go/main.go": "IMPLEMENTATION",
    "rs/lib.rs": "IMPLEMENTATION",
    "rb/a.rb": "IMPLEMENTATION",
    "run.sh": "IMPLEMENTATION",
    "db/schema.sql": "IMPLEMENTATION",
    "Script.PY": "OTHER",
    "src/main.cs": "OTHER",
    "tests/data.json": "OTHER",
    # covers the rest: a root-level match for each **/ pattern, and a near miss for each folder rule and extension
    "openapi-v1.yml": "SPECIFICATION",
    "openapi.json": "SPECIFICATION",
    "openapi.yml.txt": "OTHER",
    "myopenapi.json": "OTHER",
    "specs": "OTHER",
    "docs/specs.md": "OTHER",
    "docs/spec": "OTHER",
    "docs/specification/x.md": "OTHER",
    "docs/architectures/x.md": "OTHER",
    "src/docs/architecture/x.md": "OTHER",
    "docs/adr": "OTHER",
    "docs/adrs/0001.md": "OTHER",
    "model_config": "OTHER",
    "a.ipynb": "IMPLEMENTATION",
    "a.js": "IMPLEMENTATION",
    "a.ts": "IMPLEMENTATION",
    "A.java": "IMPLEMENTATION",
    "a.c": "IMPLEMENTATION",
    "a.h": "IMPLEMENTATION",
    "a.cpp": "IMPLEMENTATION",
    "a.hpp": "IMPLEMENTATION",
    "main.go": "IMPLEMENTATION",
    "lib.rs": "IMPLEMENTATION",
    "a.rb": "IMPLEMENTATION",
    "schema.sql": "IMPLEMENTATION",
    "a.pyc": "OTHER",
    "a.json": "OTHER",
    "a.tsx": "OTHER",
    "a.cc": "OTHER",
    "a.hh": "OTHER",
    "a.gox": "OTHER",
    "a.sqlite": "OTHER",
    "a.bash": "OTHER",
    # precedence: the first rule wins
    "requirements/check.py": "REQUIREMENT",
    "specs/gen.py": "SPECIFICATION",
    "docs/architecture/tool.py": "ARCHITECTURE",
    "docs/design/REQUIREMENTS.md": "REQUIREMENT",
    "docs/adr/openapi.yaml": "SPECIFICATION",
    # everything else, doc files included, is OTHER
    "README.md": "OTHER",
    "docs/model.md": "OTHER",
    "guide/intro.rst": "OTHER",
    "LICENSE": "OTHER",
    "Makefile": "OTHER",
    "assets/logo.png": "OTHER",
}


def analyse(api, head):
    # posts one analysis request and returns the parsed body
    r = api.post("/system/analyze", json={"repository": "octo/demo", "commit_id": head})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("path, category", CASES.items())
def test_each_path_gets_team_16s_category(path, category):
    from GitHub_Connector import rules

    assert rules.classify(path) == category


def test_the_categories_are_team_16s_six():
    from GitHub_Connector.schemas import Category

    assert {c.value for c in Category} == {"IMPLEMENTATION", "DESIGN", "ARCHITECTURE", "SPECIFICATION", "REQUIREMENT", "OTHER"}
    used = {r["category"] for r in json.loads(RULES.read_text())["rules"]}
    assert used == {"IMPLEMENTATION", "DESIGN", "ARCHITECTURE", "SPECIFICATION", "REQUIREMENT"}


def test_an_analysis_reports_the_categories(api, make_repo):
    picked = ["docs/architecture/overview.md", "docs/model.md", "specs/api.yaml", "src/model.py", "requirements.txt"]
    repo = make_repo()
    repo.commit({"seed.txt": "0\n"})
    head = repo.commit({path: f"{path}\n" for path in picked})
    got = {c["path"]: c["category"] for c in analyse(api, head)["changes"]}
    assert got == {path: CASES[path] for path in picked}


def test_renamed_file_is_classified_by_its_new_path(api, make_repo):
    repo = make_repo()
    text = "".join(f"line {i}\n" for i in range(30))
    repo.commit({"notes.py": text})
    change = analyse(api, repo.commit({"notes.py": None, "docs/design/notes.md": text}))["changes"][0]
    assert (change["change_type"], change["category"]) == ("RENAMED", "DESIGN")


def test_config_version_follows_the_rules_file(api, make_repo, tmp_path, monkeypatch):
    repo = make_repo()
    repo.commit({"seed.txt": "0\n"})
    head = repo.commit({"a.py": "a\n"})
    first, again = analyse(api, head)["config_version"], analyse(api, head)["config_version"]
    assert first == again and isinstance(first, str) and len(first) <= 16

    edited = tmp_path / "rules.json"
    data = json.loads(RULES.read_text())
    data["rules"].insert(0, {"pattern": "**/*.py", "category": "DESIGN"})
    edited.write_text(json.dumps(data))
    monkeypatch.setenv("DRIFTER_RULES_FILE", str(edited))
    from GitHub_Connector.settings import get_settings

    get_settings.cache_clear()
    body = analyse(api, head)
    assert body["config_version"] != first
    assert body["changes"][0]["category"] == "DESIGN"
