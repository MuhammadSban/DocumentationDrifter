# covers ticket 11: the labelled test repo, run through the API offline and against its public copy online

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import testrepo  # noqa: E402

# names the published test repo, DRIFTER_TEST_REPO overrides it and an empty value skips the online tests
PUBLIC_REPO = os.environ.get("DRIFTER_TEST_REPO", testrepo.PUBLIC_REPO)
from conftest import LOCAL_TESTREPO as LOCAL_NAME  # noqa: E402


@pytest.fixture
def local_api(api, built, monkeypatch):
    # points the remote base URL at the built copy
    monkeypatch.setenv("DRIFTER_REMOTE_BASE_URL", built[0].as_uri() + "/")
    from GitHub_Connector.settings import get_settings

    get_settings.cache_clear()
    return api


def check(api, repository, label, entry):
    # sends one label's request and checks the manifest's expected answer
    r = api.post("/system/analyze", json={"repository": repository, **entry["request"]})
    expect = entry["expect"]
    assert r.status_code == expect["status"], f"{label}: {r.text}"
    body = r.json()
    if expect["status"] != 200:
        assert body["code"] == expect["code"], label
        return body
    for key in ("head_commit", "base_commit", "changes", "skipped"):
        assert body[key] == expect[key], f"{label}: {key} differs"
    # fetches the run straight back, before a spin-down can wipe it
    assert api.get(f"/system/analysis/{body['analysis_id']}").content == r.content, label
    return body


def test_building_twice_gives_the_same_shas(built, tmp_path):
    again = testrepo.build(tmp_path / "again.git")
    assert again == built[2]


def test_manifest_lists_every_label(built):
    assert sorted(built[2]["labels"]) == testrepo.LABELS


@pytest.mark.parametrize("label", testrepo.LABELS)
def test_label_offline(local_api, built, label):
    check(local_api, LOCAL_NAME, label, built[2]["labels"][label])


def test_mixed_commit_repeats_identically(local_api, built):
    entry = built[2]["labels"]["mixed"]
    bodies = [check(local_api, LOCAL_NAME, "mixed", entry) for _ in range(3)]
    strip = [{k: v for k, v in b.items() if k not in ("analysis_id", "created_at")} for b in bodies]
    assert strip[0] == strip[1] == strip[2]


def test_mixed_commit_reports_every_touched_path(local_api, built):
    _, bare, manifest = built
    entry = manifest["labels"]["mixed"]
    body = check(local_api, LOCAL_NAME, "mixed", entry)
    head = entry["expect"]["head_commit"]
    raw = subprocess.run(
        ["git", "diff", "--raw", "-z", "--no-renames", "--no-abbrev", f"{head}^", head],
        cwd=bare, capture_output=True, check=True,
    ).stdout.decode().split("\0")
    touched = {raw[i + 1]: raw[i] for i in range(0, len(raw) - 1, 2)}
    reported = {c["path"] for c in body["changes"]} | {c["old_path"] for c in body["changes"] if c["old_path"]}
    skipped = {s["path"] for s in body["skipped"]}
    assert skipped <= reported, "every skipped file is also a change"
    assert set(touched) == reported, "every touched path is reported, including both sides of a rename"
    assert {".assets/secret.png", ".env.example"} <= skipped


@pytest.fixture
def public_api(target, github_env):
    # reaches the public test repo through GitHub, in-process or at DRIFTER_TARGET_URL
    if not PUBLIC_REPO:
        pytest.skip("DRIFTER_TEST_REPO is empty, so the online test-repo checks are off")
    return target


@pytest.mark.network
@pytest.mark.parametrize("label", testrepo.LABELS)
def test_label_online(public_api, built, label):
    check(public_api, PUBLIC_REPO, label, built[2]["labels"][label])

