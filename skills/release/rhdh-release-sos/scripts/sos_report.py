#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""SoS release check-in CLI — timeline-aware checks from references/sos-checks.md."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

_scripts_dir = Path(__file__).resolve().parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

import _release_bridge as bridge_mod  # noqa: E402
import sos_checks as checks_mod  # noqa: E402
import sos_report_format as format_mod  # noqa: E402


def _today(as_of: str | None) -> date:
    if as_of:
        return checks_mod._parse_iso(as_of)
    return datetime.now(timezone.utc).date()


def _fetch_milestones(version: str) -> dict[str, str]:
    jql_mod, release_mod, _rf = bridge_mod.import_release_modules()
    release_mod._init_rich_filter()
    active_jql = jql_mod.render("active_release")
    result = release_mod._run(["acli", "jira", "workitem", "search", "--jql", active_jql, "--json"])
    issues = json.loads(result.stdout)

    for issue in issues:
        summary = issue.get("fields", {}).get("summary", "")
        if version not in summary:
            continue
        detail = release_mod._acli_view_json(issue["key"])
        desc_field = detail.get("fields", {}).get("description", {})
        return release_mod._extract_milestone_dates(desc_field)

    raise ValueError(
        f"RHDH {version} is not among active releases from Jira. "
        "Use /rhdh-release-schedule for planned versions."
    )


def _build_jql(query: str, version: str, jql_mod, rf_mod) -> str:
    text = query.strip()
    static_match = re.fullmatch(r'static\s+"([^"]+)"(?:\s+\+\s+(.+))?', text, flags=re.IGNORECASE)
    if static_match:
        fragment = rf_mod.static_filter(static_match.group(1))
        if not fragment:
            raise ValueError(f'Rich Filter static filter not found: "{static_match.group(1)}"')
        extra = (static_match.group(2) or "").strip()
        return jql_mod.compose_fragment(fragment, version=version, extra=extra or None)

    template_match = re.fullmatch(r"template\s+(\S+)", text, flags=re.IGNORECASE)
    if template_match:
        return jql_mod.render(template_match.group(1), version=version)

    queue_match = re.fullmatch(r'queue\s+"([^"]+)"', text, flags=re.IGNORECASE)
    if queue_match:
        fragment = rf_mod.rich_queue(queue_match.group(1))
        if not fragment:
            raise ValueError(f'Rich Filter queue not found: "{queue_match.group(1)}"')
        return jql_mod.compose_fragment(fragment, version=version)

    raise ValueError(
        f'Unsupported query {query!r}. Use static "Name" [+ extra JQL], '
        'template NAME, or queue "Name".'
    )


def _team_jql(base_jql: str, cloud_id: str) -> str:
    return f'{base_jql} AND "Team[Team]" = "{cloud_id}"'


def _count_jql(jql: str, release_mod, fmt) -> tuple[int | None, str, str | None]:
    try:
        return release_mod._acli_count(jql, fmt), "ok", None
    except Exception as exc:  # noqa: BLE001
        return None, "unverified", str(exc)


def _run_team_breakdown(
    base_jql: str,
    teams: list[dict],
    release_mod,
    jql_mod,
    fmt,
) -> list[dict]:
    rows = []
    for team in teams:
        cloud_id = team.get("cloud_id", "")
        if not cloud_id:
            continue
        team_jql = _team_jql(base_jql, cloud_id)
        count, status, error = _count_jql(team_jql, release_mod, fmt)
        rows.append(
            {
                "team_name": team["team_name"],
                "cloud_id": cloud_id,
                "count": count,
                "status": status,
                "error": error,
                "jira_url": jql_mod.jira_url(team_jql),
            }
        )
    return rows


def _run_check(
    row: checks_mod.CheckRow,
    version: str,
    release_mod,
    jql_mod,
    rf_mod,
    fmt,
    teams: list[dict],
) -> dict:
    jql = _build_jql(row.query, version, jql_mod, rf_mod)
    url = jql_mod.jira_url(jql)
    count, status, error = _count_jql(jql, release_mod, fmt)

    return {
        "id": row.when_raw.lower().replace(" ", "-"),
        "title": row.title,
        "when": row.when_raw,
        "resolved_date": row.resolved_date.isoformat() if row.resolved_date else None,
        "query": row.query,
        "count": count,
        "status": status,
        "error": error,
        "jira_url": url,
        "teams": _run_team_breakdown(jql, teams, release_mod, jql_mod, fmt),
    }


def _milestone_summary(milestones: dict[str, str], as_of: date) -> list[dict]:
    rows = []
    for key, label in checks_mod._SECTION_ORDER:
        raw = milestones.get(key, "TBD")
        days_until = None
        if raw not in ("", "TBD", "N/A"):
            days_until = (checks_mod._parse_iso(raw) - as_of).days
        rows.append(
            {
                "milestone": label,
                "key": key,
                "date": raw,
                "days_until": days_until,
            }
        )
    return rows


def build_report(version: str, *, as_of: date | None = None, execute: bool = True) -> dict:
    as_of = as_of or _today(None)
    jql_mod, release_mod, rf_mod = bridge_mod.import_release_modules()
    from _support import OutputFormatter  # noqa: PLC0415

    release_mod._init_rich_filter()

    milestones = _fetch_milestones(version)
    rows = checks_mod.attach_dates(checks_mod.load_checks(), milestones)
    due, upcoming, active_section = checks_mod.select_checks(
        rows, as_of=as_of, milestones=milestones
    )

    fmt = OutputFormatter(mode="json")
    teams = release_mod._fetch_teams(category="Engineering") if execute else []
    executed = []
    if execute:
        for row in due:
            executed.append(_run_check(row, version, release_mod, jql_mod, rf_mod, fmt, teams))

    return format_mod.enrich_report(
        {
            "version": version,
            "as_of": as_of.isoformat(),
            "active_section": {
                "title": active_section.title,
                "milestone_key": active_section.milestone_key,
            },
            "milestones": _milestone_summary(milestones, as_of),
            "checks_due": [
                {
                    "title": row.title,
                    "when": row.when_raw,
                    "resolved_date": row.resolved_date.isoformat() if row.resolved_date else None,
                    "query": row.query,
                }
                for row in due
            ],
            "checks_upcoming": [
                {
                    "title": row.title,
                    "when": row.when_raw,
                    "resolved_date": row.resolved_date.isoformat() if row.resolved_date else None,
                    "query": row.query,
                }
                for row in upcoming
            ],
            "results": executed,
        }
    )


def cmd_check(_args: argparse.Namespace) -> None:
    _, release_mod, _rf = bridge_mod.import_release_modules()
    from _support import OutputFormatter  # noqa: PLC0415

    fmt = OutputFormatter(mode="json")
    release_mod._init_rich_filter()
    release_mod.cmd_check(_args, fmt)


def cmd_plan(args: argparse.Namespace) -> None:
    report = build_report(args.version, as_of=_today(args.date), execute=False)
    print(json.dumps({"success": True, "data": report}, indent=2))


def cmd_run(args: argparse.Namespace) -> None:
    report = build_report(args.version, as_of=_today(args.date), execute=True)
    print(json.dumps({"success": True, "data": report}, indent=2))
    if not args.json:
        print()
        print(report["report_markdown"])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="RHDH SoS release check-in")
    parser.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Verify prerequisites")

    plan = sub.add_parser("plan", help="List due and upcoming checks without Jira counts")
    plan.add_argument("version", help="Release version, e.g. 2.1.0")
    plan.add_argument("--date", help="As-of date (YYYY-MM-DD); default is today")

    run = sub.add_parser("run", help="Run due checks and return counts")
    run.add_argument("version", help="Release version, e.g. 2.1.0")
    run.add_argument("--date", help="As-of date (YYYY-MM-DD); default is today")

    args = parser.parse_args(argv)
    handlers = {"check": cmd_check, "plan": cmd_plan, "run": cmd_run}
    handlers[args.command](args)


if __name__ == "__main__":
    main()
