# checks provider failures and unusual Git paths through the HTTP API, replacing only provider HTTP

import json
from types import SimpleNamespace

import httpx
import pytest

from repos import git


@pytest.fixture
def check(monkeypatch):
    # replaces the SDK's HTTP transport, keeping request options, decoding and finding validation real
    from google import genai

    original = genai.Client
    state = SimpleNamespace(statuses=[200], findings=[])

    def respond(request):
        status = state.statuses.pop(0) if len(state.statuses) > 1 else state.statuses[0]
        if status != 200:
            return httpx.Response(status, json={"error": {"code": status, "message": "provider unavailable"}})
        return httpx.Response(200, json={
            "status": "completed", "steps": [{"type": "model_output", "content": [
                {"type": "text", "text": json.dumps({"findings": state.findings})},
            ]}],
        })

    def client(*, http_options):
        http_options.client_args = {"transport": httpx.MockTransport(respond)}
        return original(api_key="offline-fixture-key", http_options=http_options)

    monkeypatch.setenv("GEMINI_API_KEY", "offline-fixture-key")
    monkeypatch.setattr(genai, "Client", client)
    return state


def test_retryable_provider_failure_fails_the_analysis_without_retrying(api, make_repo, check):
    repo = make_repo()
    repo.commit({"src/app.py": "def before(): pass\n", "README.md": "Call before().\n"})
    head = repo.commit({"src/app.py": "def after(): pass\n"})
    check.statuses = [503, 200]

    response = api.post("/system/analyze", json={"repository": "octo/demo", "commit_id": head})

    assert response.status_code == 500
    assert response.json()["code"] == "LLM_UNAVAILABLE"


def test_line_break_in_a_doc_name_preserves_all_documentation(api, make_repo, check):
    repo = make_repo()
    base = repo.commit({"src/app.py": "def before(): pass\n"})
    doc = git("hash-object", "-w", "--stdin", cwd=repo.work, input=b"Call before().\n")
    code = git("hash-object", "-w", "--stdin", cwd=repo.work, input=b"def after(): pass\n")
    src = git("mktree", "-z", cwd=repo.work, input=f"100644 blob {code}\tapp.py\0".encode())
    tree = git("mktree", "-z", cwd=repo.work, input=(
        f"100644 blob {doc}\ta\nb.md\0"
        f"100644 blob {doc}\tz.md\0"
        f"040000 tree {src}\tsrc\0"
    ).encode())
    head = git("commit-tree", tree, "-p", base, "-m", "docs with a line break", cwd=repo.work)
    git("push", "--quiet", "origin", f"{head}:refs/heads/main", cwd=repo.work)
    check.findings = [
        {"code_file": "src/app.py", "documentation_file": path, "explanation": "before was renamed"}
        for path in ("a\nb.md", "z.md")
    ]

    response = api.post("/system/analyze", json={
        "repository": "octo/demo", "commit_id": head, "base_commit": base,
    })

    assert response.status_code == 200, response.text
    body = response.json()
    assert [f["documentation_file"] for f in body["issues"]] == ["a\nb.md", "z.md"]
    assert api.get(f"/system/analysis/{body['analysis_id']}").json() == body
