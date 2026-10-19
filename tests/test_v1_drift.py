# calls the real drift check against Gemini, run with -s to read the finding it returns

import os
import time

import pytest

from GitHub_Connector.schemas import Category
from LLM_Shell import llm

pytestmark = pytest.mark.live_llm

# bounds the call, a check with no deadline waits on the network for as long as it takes
BUDGET = 60

# plants one unmistakable drift: the function was renamed, the doc still names the old one
BEFORE = '''\
def fetch_commit(sha: str) -> str:
    """Returns the commit body for sha."""
    return sha
'''
AFTER = '''\
def get_commit(sha: str, *, verify: bool = True) -> str:
    """Returns the commit body for sha."""
    return sha
'''
DOC = '''\
# Connector

Call `fetch_commit(sha)` to read one commit. It takes a single argument.
'''


def test_check_finds_the_renamed_function():
    if not os.environ.get(llm.KEY):
        pytest.skip(f"{llm.KEY} is not set")

    code = [llm.CodeFile(path="src/fetch.py", category=Category.IMPLEMENTATION, base=BEFORE, head=AFTER)]
    docs = [llm.DocFile(path="docs/connector.md", text=DOC)]

    findings = llm.check(code, docs, time.monotonic() + BUDGET)
    for f in findings:
        print(f"\n{f.documentation_file} <- {f.code_file} ({f.issue_type}, {f.verification_status})")
        print(f"  {f.explanation}")

    assert len(findings) == 1
    assert findings[0].documentation_file == "docs/connector.md"
    assert findings[0].code_file == "src/fetch.py"


def test_check_is_quiet_when_the_doc_still_matches():
    if not os.environ.get(llm.KEY):
        pytest.skip(f"{llm.KEY} is not set")

    code = [llm.CodeFile(path="src/fetch.py", category=Category.IMPLEMENTATION, base=BEFORE, head=BEFORE)]
    docs = [llm.DocFile(path="docs/connector.md", text=DOC)]

    findings = llm.check(code, docs, time.monotonic() + BUDGET)
    print(f"\nunchanged code gave {len(findings)} findings")
    assert findings == []


def test_the_api_reports_drift_end_to_end(api, make_repo):
    # the whole path: clone, classify, gather, ask the model, save the run
    if not os.environ.get(llm.KEY):
        pytest.skip(f"{llm.KEY} is not set")

    repo = make_repo()
    repo.commit({"src/fetch.py": BEFORE, "docs/connector.md": DOC})
    head = repo.commit({"src/fetch.py": AFTER})

    r = api.post("/system/analyze", json={"repository": "octo/demo", "commit_id": head})
    assert r.status_code == 200, r.text
    body = r.json()
    for f in body["issues"]:
        print(f"\n{f['documentation_file']} <- {f['code_file']} ({f['issue_type']}, {f['verification_status']})")
        print(f"  {f['explanation']}")

    assert [(f["code_file"], f["documentation_file"]) for f in body["issues"]] == [
        ("src/fetch.py", "docs/connector.md")
    ]
    # the saved run carries the findings byte for byte
    assert api.get(f"/system/analysis/{body['analysis_id']}").json()["issues"] == body["issues"]
