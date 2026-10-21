"""Tests for the downstream catalog index status script."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    PROJECT_ROOT
    / "skills"
    / "ci"
    / "rhdh-plugin-catalog-index-status-and-update-flow"
    / "scripts"
    / "catalog_index_status.py"
)
sys.path.insert(0, str(SCRIPT_PATH.parent))

import catalog_index_status as status  # noqa: E402

DOWNSTREAM = """
### Failed (1)

| Plugin | Package | Version | Failed Stage | Reason |
| --- | --- | --- | --- | --- |
| [rbac](https://example.test/workspaces/rbac/metadata/rbac.yaml) | `@pkg/rbac` | 2.3.6 | Index | missing quay.io/rhdh/rbac:2.2.0--2.3.6 |

### Outdated (1)

| Plugin | Package | Requested Tag | Resolved Tag | OCI Reference |
| --- | --- | --- | --- | --- |
| [topology](https://example.test/workspaces/topology/metadata/topology.yaml) | `@pkg/topology` | `2.2.0--3.0.7` | `2.2.0--3.0.1` | quay.io/rhdh/topology:2.2.0--3.0.1 |

### BS Mismatch (1)

| Plugin | Package | Version |
| --- | --- | --- |
| [scorecard](https://example.test/workspaces/scorecard/metadata/scorecard.yaml) | `@pkg/scorecard` | 1.0.0 |
"""

UPSTREAM = """
### Failed (1)

| Plugin | Package | Version | Reason |
| --- | --- | --- | --- |
| [community](https://example.test/workspaces/community/metadata/community.yaml) | `@pkg/community` | 1.2.3 | missing |
"""


def _completed(stdout: str = "", code: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=code, stdout=stdout, stderr="")


def _write_package(root: Path, relative: str, name: str, version: str) -> None:
    path = root / "workspaces" / relative / "package.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"name": name, "version": version}), encoding="utf-8")


def test_help_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "check-login" in result.stdout


def test_login_refusal_matches_kfux_markers() -> None:
    assert status.login_is_refused(1, "")
    assert status.login_is_refused(0, "You must be logged in to the server")
    assert not status.login_is_refused(0, "nboldt")


def test_index_flags_follow_trigger_respin_rule() -> None:
    assert status.index_flags("main", "release-2.1") == ["--next"]
    assert status.index_flags("release-2.1", "release-2.1") == [
        "--overlays-branch",
        "release-2.1",
        "--latest",
    ]
    assert status.index_flags("release-2.0", "release-2.1") == [
        "--overlays-branch",
        "release-2.0",
    ]


def test_highest_release_branch_sorts_numeric() -> None:
    def runner(_argv: list[str]) -> subprocess.CompletedProcess[str]:
        return _completed("origin/release-2.0\norigin/release-2.1\norigin/release-10.0\n")

    assert status.highest_release_branch(Path("."), runner) == "release-10.0"


def test_resolve_version_uses_release_branch_when_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if "ls-remote" in argv:
            return _completed("abc\trefs/heads/release-2.2")
        return _completed("origin/release-2.1\n")

    monkeypatch.setattr(status, "_run", runner)
    payload = status.resolve_target(
        branch=None, version="2.2.0", catalog_root=tmp_path, runner=runner
    )
    assert payload["branch"] == "release-2.2"
    assert payload["version"] == "2.2.0"


def test_report_splits_respin_sync_and_upstream(tmp_path: Path) -> None:
    _write_package(tmp_path, "rbac/plugins/rbac", "@pkg/rbac", "2.3.6")
    _write_package(tmp_path, "topology/plugins/topology", "@pkg/topology", "3.0.1")
    payload = status.build_report(
        downstream_text=DOWNSTREAM,
        upstream_text=UPSTREAM,
        catalog_root=tmp_path,
        version="2.2.0",
    )
    actions = payload["actions"]
    assert actions["respin"][0]["path"] == "rbac/plugins/rbac"
    assert actions["respin"][0]["command"][-2:] == ["rbac/plugins/rbac", "--nopush"]
    assert "--community" not in actions["respin"][0]["command"]
    assert actions["sync"][0]["workspace"] == "topology"
    assert actions["sync"][0]["installedVersion"] == "3.0.1"
    assert "topology" in actions["syncCommand"]
    assert "rbac" not in actions["syncCommand"]
    packages = [row["package"] for row in actions["reportOnly"]]
    assert "@pkg/scorecard" in packages
    assert "@pkg/community" in packages


def test_wait_returns_succeeded_without_following_logs(tmp_path: Path) -> None:
    listed = {
        "items": [
            {
                "metadata": {
                    "name": "plugin-build",
                    "creationTimestamp": "2026-10-21T15:00:00Z",
                }
            }
        ]
    }
    finished = {
        "kind": "PipelineRun",
        "status": {"conditions": [{"type": "Succeeded", "status": "True", "reason": "Succeeded"}]},
    }

    def runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
        if argv[1:3] == ["get", "pipelinerun"] and "-l" in argv:
            return _completed(json.dumps(listed))
        if argv[1:3] == ["get", "pipelinerun"]:
            return _completed(json.dumps(finished))
        return _completed("", 1)

    payload = status.wait_for_application(
        namespace="rhdh-tenant",
        application="rhdh-plugin-catalog-2",
        since="2026-10-21T14:00:00Z",
        log_dir=tmp_path,
        runner=runner,
        follow_logs=False,
        sleeper=lambda _seconds: None,
    )
    assert payload["runs"][0]["succeeded"] is True
    assert payload["konfluxUrl"].endswith("/rhdh-plugin-catalog-2/activity/pipelineruns")
