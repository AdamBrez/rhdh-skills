#!/usr/bin/env python3
"""Resolve a catalog release and report which downstream plugins can be rebuilt.

The script prints JSON on stdout and does not prompt, commit, or push.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# Same server and console page kfuxRelease.sh prints when oc is not logged in.
KONFLUX_SERVER = "https://api.stone-prod-p02.hjvn.p1.openshiftapps.com:6443"
KONFLUX_CONSOLE = (
    "https://console-openshift-console.apps.stone-prod-p02.hjvn.p1.openshiftapps.com"
    "/k8s/cluster/projects/rhdh-tenant"
)
KONFLUX_UI = (
    "https://konflux-ui.apps.stone-prod-p02.hjvn.p1.openshiftapps.com/ns/rhdh-tenant/applications"
)
RHDH_PACKAGE_URL = (
    "https://raw.githubusercontent.com/redhat-developer/rhdh/refs/heads/{branch}/package.json"
)
WIKI_PAGE_URL = (
    "https://raw.githubusercontent.com/wiki/redhat-developer/"
    "rhdh-plugin-export-overlays/Plugin-Catalog-Status-{branch}.md"
)
CATALOG_REMOTE = "git@gitlab.cee.redhat.com:rhidp/rhdh-plugin-catalog.git"
APPLICATION_LABEL = "appstudio.openshift.io/application"
PACKAGE_JSON = "package.json"
WORKSPACES = "workspaces"
PIPELINE_RUN = "pipelinerun"
ARCHIVED_PIPELINE_RUN = "pipelineruns.kubearchive.org"
LOGIN_MARKERS = ("You must be logged in", "cannot get resource", "Error", "Forbidden")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
BRANCH_RE = re.compile(r"^(?:main|release-\d+\.\d+)$")
RELEASE_RE = re.compile(r"^release-(\d+)\.(\d+)$")
LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
WORKSPACE_RE = re.compile(r"/workspaces/([^/]+)/")
SKIP_DIRS = {"node_modules", "dist", "dist-dynamic", ".git"}
HEADER_KEYS = {
    "plugin": "plugin",
    "package": "package",
    "version": "version",
    "requested tag": "requestedTag",
    "resolved tag": "resolvedTag",
    "oci reference": "ociReference",
    "reason": "reason",
    "failed stage": "failedStage",
}
SECTION_NAMES = {
    "failed": "failed",
    "outdated": "outdated",
    "bs mismatch": "bsMismatch",
    "backstage mismatch": "bsMismatch",
}
TERMINAL_REASONS = {
    "Succeeded",
    "Failed",
    "PipelineRunTimeout",
    "TimedOut",
    "Cancelled",
    "PipelineRunCancelled",
}
Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def login_hint() -> str:
    """Tell the user how to obtain a Konflux oc session."""
    return (
        "You must be logged into the Konflux cluster before this skill continues.\n"
        f"oc login --server={KONFLUX_SERVER}\n"
        f"Copy login command from {KONFLUX_CONSOLE}\n"
        "Open the rhdh-tenant project, click your username, Copy login command, Display token."
    )


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a command and capture both streams."""
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def login_is_refused(returncode: int, text: str) -> bool:
    """Match the kfuxRelease.sh oc whoami failure check."""
    if returncode != 0:
        return True
    return any(marker in text for marker in LOGIN_MARKERS)


def check_login(runner: Runner = _run) -> dict[str, Any]:
    """Return whether oc whoami shows a usable Konflux session."""
    proc = runner(["oc", "whoami"])
    text = (proc.stdout + proc.stderr).strip()
    refused = login_is_refused(proc.returncode, text)
    payload: dict[str, Any] = {"ok": not refused, "whoami": text}
    if refused:
        payload["loginHint"] = login_hint()
    return payload


def _fetch_text(url: str) -> str:
    """GET a public URL and return the body.

    Retries once after a 2-second backoff for transient network errors
    and server-side (5xx) HTTP failures.
    """
    request = urllib.request.Request(url, headers={"User-Agent": "rhdh-skills"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code < 500:
            raise
        first_error: urllib.error.URLError = exc
    except urllib.error.URLError as exc:
        first_error = exc
    time.sleep(2)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")
    except urllib.error.URLError:
        raise first_error from None


def rhdh_version(branch: str) -> str:
    """Read the x.y.z version from redhat-developer/rhdh package.json on branch."""
    payload = json.loads(_fetch_text(RHDH_PACKAGE_URL.format(branch=branch)))
    version = payload.get("version")
    if not isinstance(version, str) or VERSION_RE.fullmatch(version) is None:
        raise ValueError(f"rhdh package.json on {branch} has no x.y.z version")
    return version


def _release_key(name: str) -> tuple[int, int]:
    """Sort key for a release-X.Y branch name."""
    match = RELEASE_RE.fullmatch(name)
    if match is None:
        return (0, 0)
    return (int(match.group(1)), int(match.group(2)))


def remote_has_branch(branch: str, catalog_root: Path | None, runner: Runner = _run) -> bool:
    """Return whether origin advertises branch."""
    if catalog_root is None:
        argv = ["git", "ls-remote", "--heads", CATALOG_REMOTE, f"refs/heads/{branch}"]
    else:
        argv = [
            "git",
            "-C",
            str(catalog_root),
            "ls-remote",
            "--heads",
            "origin",
            f"refs/heads/{branch}",
        ]
    return bool(runner(argv).stdout.strip())


def highest_release_branch(catalog_root: Path, runner: Runner = _run) -> str | None:
    """Return the highest origin/release-X.Y branch, using the triggerRespin.sh rule."""
    proc = runner(
        [
            "git",
            "-C",
            str(catalog_root),
            "for-each-ref",
            "--format=%(refname:short)",
            "refs/remotes/origin/release-*",
        ]
    )
    names = []
    for line in proc.stdout.splitlines():
        short = line.removeprefix("origin/")
        if RELEASE_RE.fullmatch(short):
            names.append(short)
    if not names:
        return None
    return max(names, key=_release_key)


def index_flags(branch: str, highest: str | None) -> list[str]:
    """Flags for the downstream update-index.sh run."""
    if branch == "main":
        return ["--next"]
    flags = ["--overlays-branch", branch]
    if highest is not None and branch == highest:
        flags.append("--latest")
    return flags


def application_name(catalog_root: Path) -> str | None:
    """Read the Konflux application from the catalog-index PipelineRun."""
    tekton = catalog_root / ".tekton"
    if not tekton.is_dir():
        return None
    for path in sorted(tekton.glob("plugin-catalog-index-*-push.yaml")):
        text = path.read_text(encoding="utf-8")
        match = re.search(rf"{re.escape(APPLICATION_LABEL)}:\s*(\S+)", text)
        if match:
            return match.group(1)
    return None


def konflux_activity_url(application: str) -> str:
    """PipelineRun activity page for one Konflux application."""
    return f"{KONFLUX_UI}/{application}/activity/pipelineruns"


def resolve_target(
    *,
    branch: str | None,
    version: str | None,
    catalog_root: Path | None,
    runner: Runner = _run,
) -> dict[str, Any]:
    """Fill in the missing half of a branch or x.y.z pair."""
    if branch is None and version is None:
        raise ValueError("pass a branch (main or release-X.Y) or a version x.y.z")
    if version is not None and VERSION_RE.fullmatch(version) is None:
        raise ValueError("version must be x.y.z")
    if branch is not None and BRANCH_RE.fullmatch(branch) is None:
        raise ValueError("branch must be main or release-X.Y")
    resolved_branch = branch
    if resolved_branch is None and version is not None:
        candidate = f"release-{version.rsplit('.', 1)[0]}"
        resolved_branch = (
            candidate if remote_has_branch(candidate, catalog_root, runner) else "main"
        )
    assert resolved_branch is not None
    resolved_version = version if version is not None else rhdh_version(resolved_branch)
    highest = highest_release_branch(catalog_root, runner) if catalog_root else None
    payload: dict[str, Any] = {
        "branch": resolved_branch,
        "version": resolved_version,
        "indexFlags": index_flags(resolved_branch, highest),
        "highestRelease": highest,
    }
    if catalog_root is not None:
        app = application_name(catalog_root)
        if app:
            payload["application"] = app
            payload["konfluxUrl"] = konflux_activity_url(app)
    return payload


def _header_key(cell: str) -> str:
    """Map a markdown header cell onto a stable field name."""
    plain = re.sub(r"[^a-z0-9]+", " ", cell.lower()).strip()
    return HEADER_KEYS.get(plain, plain)


def _cells(line: str) -> list[str]:
    """Split one markdown table row into stripped cells."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator(cells: list[str]) -> bool:
    """True for the |---| row under a header."""
    return bool(cells) and all(set(cell) <= set("-: ") and cell for cell in cells)


def parse_table(lines: list[str]) -> list[dict[str, str]]:
    """Parse the first markdown table in lines."""
    headers: list[str] | None = None
    rows: list[dict[str, str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            if headers:
                break
            continue
        cells = _cells(stripped)
        if _is_separator(cells):
            continue
        if headers is None:
            headers = [_header_key(cell) for cell in cells]
            continue
        rows.append(dict(zip(headers, cells)))
    return rows


def _section_name(heading: str) -> str | None:
    """Map a ### heading onto failed, outdated, or bsMismatch."""
    plain = re.sub(r"[^a-z ]+", "", heading.lower())
    for needle, name in SECTION_NAMES.items():
        if needle in plain:
            return name
    return None


def parse_status_markdown(text: str) -> dict[str, list[dict[str, str]]]:
    """Pull Failed, Outdated, and BS Mismatch tables out of a status page."""
    sections: dict[str, list[dict[str, str]]] = {
        "failed": [],
        "outdated": [],
        "bsMismatch": [],
    }
    current: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        if current is None:
            return
        rows = parse_table(buffer)
        if rows and not sections[current]:
            sections[current] = rows

    for line in text.splitlines():
        if line.startswith("### "):
            flush()
            buffer = []
            current = _section_name(line[4:])
            continue
        if current is not None:
            buffer.append(line)
    flush()
    return sections


def _plain_cell(value: str) -> str:
    """Drop backticks and surrounding space from a table cell."""
    return value.replace("`", "").strip()


def _link_url(value: str) -> str | None:
    """Return the first markdown link target in a cell."""
    match = LINK_RE.search(value)
    return match.group(2) if match else None


def _workspace_from_row(row: dict[str, str]) -> str | None:
    """Read the overlays workspace name from a plugin metadata link."""
    for value in row.values():
        url = _link_url(value) or value
        match = WORKSPACE_RE.search(url)
        if match:
            return match.group(1)
    return None


def _npm_name(row: dict[str, str]) -> str:
    """Return the package name without backticks."""
    return _plain_cell(row.get("package", ""))


def _requested_plugin_version(row: dict[str, str]) -> str:
    """Plugin version from an outdated requested tag, else the Version column."""
    requested = _plain_cell(row.get("requestedTag", ""))
    if "--" in requested:
        return requested.split("--", 1)[1]
    return _plain_cell(row.get("version", ""))


def _iter_package_files(workspace_dir: Path) -> list[Path]:
    """package.json files under a workspace, skipping install and build output."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(workspace_dir):
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]
        if PACKAGE_JSON in filenames:
            found.append(Path(dirpath) / PACKAGE_JSON)
    return found


def find_installed_package(
    catalog_root: Path, workspace: str, npm_name: str
) -> dict[str, str] | None:
    """Locate the workspace package.json whose name matches the catalog row."""
    base = catalog_root / WORKSPACES / workspace
    if not base.is_dir():
        return None
    for path in _iter_package_files(base):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("name") != npm_name:
            continue
        version = payload.get("version")
        if not isinstance(version, str):
            return None
        relative = path.parent.relative_to(catalog_root / WORKSPACES).as_posix()
        return {"version": version, "path": relative}
    return None


def _row_record(row: dict[str, str], kind: str) -> dict[str, str]:
    """Compact one status-table row for the JSON report."""
    record = {
        "kind": kind,
        "package": _npm_name(row),
        "requestedVersion": _requested_plugin_version(row),
    }
    workspace = _workspace_from_row(row)
    if workspace:
        record["workspace"] = workspace
    requested = _plain_cell(row.get("requestedTag", ""))
    if requested:
        record["requestedTag"] = requested
    return record


def sync_command(workspaces: list[str]) -> str | None:
    """sync-midstream.sh invocation for workspaces that are behind upstream."""
    names = sorted({name for name in workspaces if name})
    if not names:
        return None
    inner = "|".join(names)
    return (
        "./build/ci/sync-midstream.sh --nocommit --nopreparedsourcesref "
        f'--force-clone "^workspaces/({inner})$"'
    )


def classify_downstream(
    sections: dict[str, list[dict[str, str]]],
    *,
    catalog_root: Path,
    version: str,
) -> dict[str, Any]:
    """Split downstream rows into respin, sync, and report-only actions."""
    respin: list[dict[str, Any]] = []
    sync_rows: list[dict[str, str]] = []
    report_only = [_row_record(row, "bsMismatch") for row in sections["bsMismatch"]]
    for kind in ("failed", "outdated"):
        for row in sections[kind]:
            record = _row_record(row, kind)
            workspace = record.get("workspace")
            installed = (
                find_installed_package(catalog_root, workspace, record["package"])
                if workspace and record["package"]
                else None
            )
            if installed and installed["version"] == record["requestedVersion"]:
                path = installed["path"]
                respin.append(
                    {
                        **record,
                        "installedVersion": installed["version"],
                        "path": path,
                        "command": [
                            ".tekton/updatePLRs.sh",
                            "-v",
                            version,
                            "--trigger",
                            "--path",
                            path,
                            "--nopush",
                        ],
                    }
                )
                continue
            if installed:
                record["installedVersion"] = installed["version"]
            sync_rows.append(record)
    return {
        "respin": respin,
        "sync": sync_rows,
        "reportOnly": report_only,
        "syncCommand": sync_command([row.get("workspace", "") for row in sync_rows]),
    }


def _upstream_report(sections: dict[str, list[dict[str, str]]]) -> list[dict[str, str]]:
    """Upstream wiki failures are reported and never trigger Konflux."""
    rows: list[dict[str, str]] = []
    for kind in ("failed", "outdated", "bsMismatch"):
        rows.extend(_row_record(row, kind) for row in sections[kind])
    return rows


def build_report(
    *,
    downstream_text: str,
    upstream_text: str | None,
    catalog_root: Path,
    version: str,
) -> dict[str, Any]:
    """Classify one downstream status page and an optional upstream wiki page."""
    downstream = parse_status_markdown(downstream_text)
    actions = classify_downstream(downstream, catalog_root=catalog_root, version=version)
    upstream_rows: list[dict[str, str]] = []
    if upstream_text:
        upstream_rows = _upstream_report(parse_status_markdown(upstream_text))
    actions["reportOnly"].extend(upstream_rows)
    return {
        "version": version,
        "downstream": {key: len(rows) for key, rows in downstream.items()},
        "actions": actions,
    }


def _parse_time(value: str) -> datetime:
    """Parse an RFC3339 timestamp from oc or from --since."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _created_after(item: dict[str, Any], since: datetime) -> bool:
    """True when a PipelineRun was created at or after since."""
    stamp = item.get("metadata", {}).get("creationTimestamp")
    if not isinstance(stamp, str):
        return False
    return _parse_time(stamp) >= since


def pipelinerun_reason(obj: dict[str, Any]) -> str | None:
    """Succeeded condition reason, or None while the run is still going."""
    for condition in obj.get("status", {}).get("conditions") or []:
        if condition.get("type") != "Succeeded":
            continue
        reason = condition.get("reason")
        if isinstance(reason, str) and reason:
            return reason
        return "Succeeded" if condition.get("status") == "True" else "Failed"
    return None


def _load_json(proc: subprocess.CompletedProcess[str]) -> dict[str, Any] | None:
    """Parse oc JSON, or None when the command failed."""
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def list_new_runs(
    *,
    namespace: str,
    application: str,
    since: datetime,
    runner: Runner,
) -> list[dict[str, Any]]:
    """PipelineRuns for the application created at or after since."""
    proc = runner(
        [
            "oc",
            "get",
            PIPELINE_RUN,
            "-n",
            namespace,
            "-l",
            f"{APPLICATION_LABEL}={application}",
            "-o",
            "json",
        ]
    )
    payload = _load_json(proc) or {}
    items = payload.get("items") or []
    return [item for item in items if isinstance(item, dict) and _created_after(item, since)]


def get_pipelinerun(namespace: str, name: str, runner: Runner) -> dict[str, Any] | None:
    """Read a live PipelineRun, then the archived object if Konflux already collected it."""
    for resource in (PIPELINE_RUN, ARCHIVED_PIPELINE_RUN):
        proc = runner(["oc", "get", resource, name, "-n", namespace, "-o", "json"])
        payload = _load_json(proc)
        if payload is not None and payload.get("kind"):
            return payload
    return None


def _stream_logs(namespace: str, name: str, log_path: Path) -> tuple[subprocess.Popen[str], Any]:
    """Follow Tekton logs into log_path until the caller stops the process.

    Returns the Popen process **and** the open file handle so the caller
    can close the handle after terminating the process.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [
            "oc",
            "logs",
            "-f",
            "-n",
            namespace,
            "-l",
            f"tekton.dev/pipelineRun={name}",
            "--all-containers",
            "--prefix",
        ],
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc, handle


def follow_run(
    *,
    namespace: str,
    name: str,
    log_path: Path,
    timeout_seconds: int,
    runner: Runner,
    sleeper: Callable[[float], None] = time.sleep,
    follow_logs: bool = True,
) -> str:
    """Block until the PipelineRun reaches a terminal reason and return that reason."""
    logs: subprocess.Popen[str] | None = None
    log_handle: Any = None
    if follow_logs:
        logs, log_handle = _stream_logs(namespace, name, log_path)
    deadline = time.monotonic() + timeout_seconds
    reason = "TimedOut"
    try:
        while time.monotonic() < deadline:
            current = get_pipelinerun(namespace, name, runner)
            found = pipelinerun_reason(current) if current else None
            if found in TERMINAL_REASONS:
                reason = found
                break
            sleeper(10)
    finally:
        if logs is not None and logs.poll() is None:
            logs.terminate()
        if log_handle is not None:
            log_handle.close()
    return reason


def wait_for_application(
    *,
    namespace: str,
    application: str,
    since: str,
    log_dir: Path,
    appear_timeout: int = 900,
    run_timeout: int = 7200,
    runner: Runner = _run,
    sleeper: Callable[[float], None] = time.sleep,
    follow_logs: bool = True,
) -> dict[str, Any]:
    """Watch new PipelineRuns for one application until each one finishes."""
    started = _parse_time(since)
    deadline = time.monotonic() + appear_timeout
    runs = list_new_runs(namespace=namespace, application=application, since=started, runner=runner)
    while not runs and time.monotonic() < deadline:
        sleeper(10)
        runs = list_new_runs(
            namespace=namespace, application=application, since=started, runner=runner
        )
    results = []
    for item in runs:
        name = item.get("metadata", {}).get("name", "")
        if not name:
            continue
        reason = follow_run(
            namespace=namespace,
            name=name,
            log_path=log_dir / f"{name}.log",
            timeout_seconds=run_timeout,
            runner=runner,
            sleeper=sleeper,
            follow_logs=follow_logs,
        )
        results.append(
            {
                "name": name,
                "reason": reason,
                "succeeded": reason == "Succeeded",
                "logFile": str(log_dir / f"{name}.log"),
            }
        )
    return {
        "application": application,
        "konfluxUrl": konflux_activity_url(application),
        "runs": results,
    }


def _emit(payload: dict[str, Any], code: int) -> int:
    """Print payload as JSON and return the process exit code."""
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return code


def _catalog_root(value: str | None) -> Path | None:
    """Resolve an optional catalog checkout path."""
    return Path(value).resolve() if value else None


def _command_check_login(_args: argparse.Namespace) -> int:
    """Exit 1 until oc whoami succeeds."""
    payload = check_login()
    if not payload["ok"]:
        print(payload["loginHint"], file=sys.stderr)
    return _emit(payload, 0 if payload["ok"] else 1)


def _command_resolve(args: argparse.Namespace) -> int:
    """Print the branch, version, index flags, and Konflux application."""
    try:
        payload = resolve_target(
            branch=args.branch,
            version=args.version,
            catalog_root=_catalog_root(args.catalog_root),
        )
    except (ValueError, urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        return _emit({"ok": False, "error": str(exc)}, 2)
    return _emit(payload, 0)


def _read_upstream(args: argparse.Namespace) -> str | None:
    """Load the wiki page from disk or from GitHub."""
    if args.upstream:
        return Path(args.upstream).read_text(encoding="utf-8")
    if args.branch:
        return _fetch_text(WIKI_PAGE_URL.format(branch=args.branch))
    return None


def _command_report(args: argparse.Namespace) -> int:
    """Classify downstream and upstream status pages."""
    catalog_root = Path(args.catalog_root).resolve()
    try:
        downstream = Path(args.downstream).read_text(encoding="utf-8")
        upstream = _read_upstream(args)
        payload = build_report(
            downstream_text=downstream,
            upstream_text=upstream,
            catalog_root=catalog_root,
            version=args.version,
        )
    except (OSError, urllib.error.URLError, ValueError) as exc:
        return _emit({"ok": False, "error": str(exc)}, 2)
    return _emit(payload, 0)


def _command_wait(args: argparse.Namespace) -> int:
    """Block until the new PipelineRuns finish and write their logs."""
    log_dir = (
        Path(args.log_dir)
        if args.log_dir
        else Path(os.environ.get("TMPDIR", "/tmp")) / "catalog-index-status"
    )
    payload = wait_for_application(
        namespace=args.namespace,
        application=args.application,
        since=args.since,
        log_dir=log_dir,
        appear_timeout=args.appear_timeout,
        run_timeout=args.run_timeout,
    )
    failed = any(not run["succeeded"] for run in payload["runs"]) or not payload["runs"]
    return _emit(payload, 1 if failed else 0)


def build_parser() -> argparse.ArgumentParser:
    """Command line for login, resolve, report, and wait."""
    parser = argparse.ArgumentParser(
        description="Report downstream plugin-catalog index gaps and watch Konflux builds."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    login = sub.add_parser("check-login", help="Refuse unless oc whoami succeeds")
    login.set_defaults(func=_command_check_login)
    resolve = sub.add_parser("resolve", help="Resolve a branch or x.y.z to both")
    resolve.add_argument("--branch", help="main or release-X.Y")
    resolve.add_argument("--version", help="RHDH version x.y.z")
    resolve.add_argument("--catalog-root", help="rhdh-plugin-catalog checkout or worktree")
    resolve.set_defaults(func=_command_resolve)
    report = sub.add_parser("report", help="Classify status pages against the worktree")
    report.add_argument("--catalog-root", required=True)
    report.add_argument("--downstream", required=True, help="docs/catalog-status.md")
    report.add_argument("--upstream", help="Local copy of the wiki page")
    report.add_argument("--branch", help="Wiki branch when --upstream is omitted")
    report.add_argument("--version", required=True, help="RHDH x.y.z for updatePLRs.sh -v")
    report.set_defaults(func=_command_report)
    wait = sub.add_parser("wait-runs", help="Follow new PipelineRuns until they finish")
    wait.add_argument("--namespace", default="rhdh-tenant")
    wait.add_argument("--application", required=True)
    wait.add_argument("--since", required=True, help="RFC3339 timestamp of the push")
    wait.add_argument("--log-dir")
    wait.add_argument("--appear-timeout", type=int, default=900)
    wait.add_argument("--run-timeout", type=int, default=7200)
    wait.set_defaults(func=_command_wait)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch one subcommand."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
