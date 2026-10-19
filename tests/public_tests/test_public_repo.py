# covers analysing our own repo through GitHub, run only while it is public

import pytest

# pins the merge of PR #2, which our history keeps on every branch
MERGE_PR_2 = "76eb691571b9bca344517c2cee46a667e7c43d46"
FIRST_PARENT = "b371a2df3314bc3937e73a61b38d19c91776a17d"


@pytest.mark.network
def test_our_public_repo_is_analysed_anonymously(api, github_env, recorded_helper, public_project):
    r = api.post("/system/analyze", json={"repository": public_project, "commit_id": MERGE_PR_2[:7]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["head_commit"], body["base_commit"]) == (MERGE_PR_2, FIRST_PARENT)
    assert [(c["path"], c["change_type"], c["category"]) for c in body["changes"]] == [
        ("Source/LLM_Shell/LLM.md", "ADDED", "OTHER"),
        ("requirements.txt", "ADDED", "OTHER"),
        ("tests/conftest.py", "ADDED", "IMPLEMENTATION"),
        ("tests/test_config.py", "ADDED", "IMPLEMENTATION"),
        ("tests/test_receiver.py", "ADDED", "IMPLEMENTATION"),
    ]
    assert not recorded_helper.exists(), "a credential helper was asked for credentials"
    assert api.get(f"/system/analysis/{body['analysis_id']}").content == r.content
