# covers cross-team tester ticket 12: more changed files than the limit give a saved 200 ERROR result, as Team 16's system does (TT-Q13)

import pytest


def analyse(api, head, **extra):
    # posts one analysis request and returns the parsed body
    r = api.post("/system/analyze", json={"repository": "octo/demo", "commit_id": head, **extra})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def wide(make_repo):
    # builds a seed, then 2000 new files, then one more, returns the three commits
    repo = make_repo()
    seed = repo.commit({"seed.txt": "0\n"})
    two_thousand = repo.commit({f"f/{n:04d}.txt": f"{n}\n" for n in range(2000)})
    one_more = repo.commit({"f/2000.txt": "2000\n"})
    return seed, two_thousand, one_more


def test_2001_changed_files_give_a_saved_error_result(api, wide):
    seed, _, one_more = wide
    body = analyse(api, one_more, base_commit=seed)
    assert body["status"] == "ERROR"
    assert body["error"] == {"code": "CHANGE_LIMIT_EXCEEDED", "message": "2001 changed files exceeds the limit of 2000"}
    assert body["changes"] == [] and body["skipped"] == [] and body["issues"] == []
    assert body["head_commit"] == one_more and body["base_commit"] == seed
    served = api.get(f"/system/analysis/{body['analysis_id']}")
    assert served.status_code == 200 and served.json() == body


def test_2000_changed_files_give_a_normal_success(api, wide):
    seed, two_thousand, _ = wide
    body = analyse(api, two_thousand, base_commit=seed)
    assert body["status"] == "SUCCESS" and body["error"] is None
    assert len(body["changes"]) == 2000


def test_the_limit_is_a_setting(api, make_repo, monkeypatch):
    from GitHub_Connector.settings import get_settings

    assert get_settings().max_changed_files == 2000
    monkeypatch.setenv("DRIFTER_MAX_CHANGED_FILES", "2")
    get_settings.cache_clear()
    repo = make_repo()
    repo.commit({"seed.txt": "0\n"})
    two = analyse(api, repo.commit({"a.txt": "a\n", "b.txt": "b\n"}))
    three = analyse(api, repo.commit({"c.txt": "c\n", "d.txt": "d\n", "e.txt": "e\n"}))
    assert two["status"] == "SUCCESS"
    assert three["status"] == "ERROR"
    assert three["error"]["message"] == "3 changed files exceeds the limit of 2"
