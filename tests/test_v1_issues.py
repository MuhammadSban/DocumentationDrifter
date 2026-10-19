# covers the v1.2 wiring: what the drift check is sent, what it fills in, and how its one failure travels
# copies main's v1.2 tests (c7e7b53), with docs found by path and docs past the budget counted but not listed

import time

import pytest

from GitHub_Connector.schemas import AnalysisError, Category, ErrorCode, Finding, IssueType

CODE_BEFORE = "def fetch_commit(sha):\n    return sha\n"
CODE_AFTER = "def get_commit(sha):\n    return sha\n"
GUIDE = "# Guide\n\nCall `fetch_commit(sha)`.\n"


class Recorder:
    # stands in for the one LLM call, so these tests need no key and no network

    def __init__(self):
        self.calls = []
        self.findings = []
        self.error = None

    def __call__(self, code, docs, deadline=None, omitted=0):
        self.calls.append({"code": code, "docs": docs, "deadline": deadline, "omitted": omitted})
        if self.error is not None:
            raise self.error
        return self.findings

    @property
    def one(self):
        # the single call the analysis should have made
        assert len(self.calls) == 1, f"{len(self.calls)} calls"
        return self.calls[0]


@pytest.fixture
def check(monkeypatch):
    # replaces LLM_Shell.llm.check, which analysis.py calls through the module
    from LLM_Shell import llm

    recorder = Recorder()
    monkeypatch.setattr(llm, "check", recorder)
    return recorder


@pytest.fixture
def budget(monkeypatch):
    # repoints the doc budget, clearing the settings cache the way v1_env does
    def _set(nbytes: int):
        from GitHub_Connector.settings import get_settings

        monkeypatch.setenv("DRIFTER_DOC_BUDGET_BYTES", str(nbytes))
        get_settings.cache_clear()

    return _set


def analyse(api, head, **extra):
    # posts one analysis request and returns the parsed body
    r = api.post("/system/analyze", json={"repository": "octo/demo", "commit_id": head, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_changed_code_and_the_docs_at_head_are_sent(api, make_repo, check):
    repo = make_repo()
    repo.commit({"src/app.py": CODE_BEFORE, "docs/guide.md": GUIDE, "README.md": "# Demo\n"})
    analyse(api, repo.commit({"src/app.py": CODE_AFTER}))

    call = check.one
    assert [(c.path, c.category, c.base, c.head) for c in call["code"]] == [
        ("src/app.py", Category.IMPLEMENTATION, CODE_BEFORE, CODE_AFTER)
    ]
    # every doc at head, not only the changed ones, in path order
    assert [d.path for d in call["docs"]] == ["README.md", "docs/guide.md"]
    assert call["omitted"] == 0
    # shares the analysis clock, so a slow check cannot outlive the deadline
    assert call["deadline"] > time.monotonic()


def test_a_renamed_file_is_sent_with_its_base_side(api, make_repo, check):
    repo = make_repo()
    repo.commit({"src/a.py": CODE_BEFORE, "docs/guide.md": GUIDE})
    analyse(api, repo.commit({"src/a.py": None, "src/b.py": CODE_BEFORE}))

    sent = check.one["code"]
    assert [(c.path, c.base, c.head) for c in sent] == [("src/b.py", CODE_BEFORE, CODE_BEFORE)]


def test_docs_that_are_not_readable_text_are_left_out_without_a_record(api, make_repo, check):
    repo = make_repo()
    repo.commit({
        "src/app.py": CODE_BEFORE,
        "docs/guide.md": GUIDE,
        "docs/logo.png": b"\x89PNG\r\n\x1a\n",       # unsupported extension
        "docs/binary.md": b"text\0more\n",            # NUL in the first bytes
        "docs/latin.txt": b"caf\xe9 notes\n",         # not UTF-8
    })
    body = analyse(api, repo.commit({"src/app.py": CODE_AFTER}))

    assert [d.path for d in check.one["docs"]] == ["docs/guide.md"]
    # none of them changed in this commit, so none of them is ours to report
    assert body["skipped"] == []


def test_docs_past_the_budget_are_counted_but_not_listed(api, make_repo, check, budget):
    repo = make_repo()
    repo.commit({"src/app.py": CODE_BEFORE, "docs/a.md": "a" * 60, "docs/b.md": "b" * 60})
    budget(100)
    body = analyse(api, repo.commit({"src/app.py": CODE_AFTER}))

    assert [d.path for d in check.one["docs"]] == ["docs/a.md"]
    assert check.one["omitted"] == 1
    # keeps skipped[] as Team 16's system gives it, by file name alone
    assert body["skipped"] == []


def test_docs_are_found_by_path_while_the_category_stays_team_16s(api, make_repo, check):
    repo = make_repo()
    repo.commit({"src/app.py": CODE_BEFORE, "notes.txt": "n\n", "requirements.txt": "x\n", "docs/design/a.md": GUIDE})
    body = analyse(api, repo.commit({"src/app.py": CODE_AFTER, "docs/design/a.md": GUIDE + "more\n"}))

    assert [d.path for d in check.one["docs"]] == ["docs/design/a.md", "notes.txt"]
    # sends a changed doc once, whole at head, never as changed code
    assert [c.path for c in check.one["code"]] == ["src/app.py"]
    assert {c["path"]: c["category"] for c in body["changes"]}["docs/design/a.md"] == "DESIGN"


def test_a_side_comes_back_empty_when_there_is_nothing_to_compare(api, make_repo, check):
    repo = make_repo()
    repo.commit({"src/app.py": CODE_BEFORE})
    # a repo with no documentation at all
    assert analyse(api, repo.commit({"src/app.py": CODE_AFTER}))["issues"] == []
    assert check.calls[0]["docs"] == []
    # a commit that changed documentation only
    assert analyse(api, repo.commit({"docs/guide.md": GUIDE}))["issues"] == []
    assert check.calls[1]["code"] == []


def test_check_asks_nothing_when_a_side_is_empty():
    # the short circuit itself, which is why an empty side needs no key and costs nothing
    from LLM_Shell import llm

    docs = [llm.DocFile(path="docs/guide.md", text=GUIDE)]
    code = [llm.CodeFile(path="src/app.py", category=Category.IMPLEMENTATION, base=None, head=CODE_AFTER)]
    assert llm.check([], docs) == []
    assert llm.check(code, []) == []


def test_findings_are_saved_sorted_by_documentation_file(api, make_repo, check):
    repo = make_repo()
    repo.commit({"src/app.py": CODE_BEFORE, "docs/a.md": GUIDE, "docs/b.md": GUIDE})
    check.findings = [
        Finding(
            finding_id=f"f-{n}",
            issue_type=IssueType.OUTDATED_DOCUMENTATION.value,
            code_file="src/app.py",
            documentation_file=doc,
            change_category=Category.IMPLEMENTATION,
            explanation="renamed",
            verification_status="PENDING_REVIEW",
        )
        for n, doc in enumerate(("docs/b.md", "docs/a.md"))
    ]
    body = analyse(api, repo.commit({"src/app.py": CODE_AFTER}))

    assert [i["documentation_file"] for i in body["issues"]] == ["docs/a.md", "docs/b.md"]
    assert body["issues"][0]["verification_status"] == "PENDING_REVIEW"
    assert body["issues"][0]["issue_type"] == "OUTDATED_DOCUMENTATION"


def test_a_failed_check_is_500_and_saves_nothing(api, make_repo, check, v1_env):
    repo = make_repo()
    repo.commit({"src/app.py": CODE_BEFORE, "docs/guide.md": GUIDE})
    check.error = AnalysisError(ErrorCode.LLM_UNAVAILABLE, "the drift check did not complete")

    r = api.post("/system/analyze", json={"repository": "octo/demo", "commit_id": repo.commit({"src/app.py": CODE_AFTER})})
    assert r.status_code == 500
    assert r.json() == {"code": "LLM_UNAVAILABLE", "message": "the drift check did not complete"}
    assert list(v1_env["runs"].iterdir()) == []


def test_added_and_deleted_names_with_spaces_are_analyzed(api, make_repo, check):
    repo = make_repo()
    repo.commit({"src/old name.py": CODE_BEFORE, "docs/guide.md": GUIDE})
    body = analyse(api, repo.commit({"src/old name.py": None, "src/new name.py": "print('new')\n"}))

    assert [(c["path"], c["change_type"]) for c in body["changes"]] == [
        ("src/new name.py", "ADDED"), ("src/old name.py", "DELETED")
    ]
    assert api.get(f"/system/analysis/{body['analysis_id']}").json() == body
