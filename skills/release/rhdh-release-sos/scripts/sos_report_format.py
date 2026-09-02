"""Render SoS check-in reports from a fixed template."""

from __future__ import annotations

_MILESTONE_ORDER = [
    ("feature_freeze", "Feature Freeze"),
    ("code_freeze", "Code Freeze"),
    ("go_no_go", "Go/No Go"),
    ("ga_announce", "GA Announce"),
]


def team_display_name(team_name: str) -> str:
    """Short label for team sub-rows."""
    name = team_name.strip()
    if name.lower().startswith("rhdh "):
        return name[5:]
    return name


def check_summary(result: dict) -> str:
    """Short summary label for the Checks table."""
    if result.get("status") == "unverified":
        return "Unverified"

    count = result.get("count")
    if count == 0:
        return "None open"
    if count == 1:
        return "1 open"
    return f"{count} open"


def _milestone_cells(report: dict) -> dict[str, str]:
    cells = {}
    for key, label in _MILESTONE_ORDER:
        row = next((item for item in report.get("milestones", []) if item["key"] == key), None)
        if row is None:
            cells[f"{key}_date"] = "TBD"
            cells[f"{key}_days"] = "TBD"
            continue
        date = row.get("date", "TBD")
        days = row.get("days_until")
        cells[f"{key}_date"] = str(date)
        cells[f"{key}_days"] = str(days) if days is not None else "TBD"
        cells[label] = row
    return cells


def _next_milestone_line(report: dict) -> str:
    for row in report.get("milestones", []):
        days = row.get("days_until")
        if days is None:
            continue
        if days >= 0:
            return f"{row['milestone']} on {row.get('date', 'TBD')} ({days} days)"
    last = report.get("milestones", [])[-1] if report.get("milestones") else None
    if last:
        return f"{last['milestone']} on {last.get('date', 'TBD')}"
    return "TBD"


def _jira_cell(link: str | None) -> str:
    return f"[Open in Jira]({link})" if link else "—"


def _check_rows(results: list[dict]) -> str:
    if not results:
        return "| _No checks due today._ | | |"
    lines = []
    for result in results:
        lines.append(
            f"| {result['title']} | {check_summary(result)} | "
            f"{_jira_cell(result.get('jira_url'))} |"
        )
        for team in result.get("teams", []):
            label = team_display_name(team["team_name"])
            lines.append(
                f"| ↳ {label} | {check_summary(team)} | {_jira_cell(team.get('jira_url'))} |"
            )
    return "\n".join(lines)


def render_report_markdown(report: dict) -> str:
    """Render the fixed SoS report template."""
    version = report["version"]
    as_of = report["as_of"]
    section = report["active_section"]["title"]
    milestone_cells = _milestone_cells(report)

    return f"""# RHDH {version} — SoS Release Check-in

| | |
|---|---|
| As of | {as_of} |
| Release phase | {section} |
| Next milestone | {_next_milestone_line(report)} |

## Milestones

| Milestone | Date | Days remaining |
|---|---|---:|
| Feature Freeze | {milestone_cells["feature_freeze_date"]} | {milestone_cells["feature_freeze_days"]} |
| Code Freeze | {milestone_cells["code_freeze_date"]} | {milestone_cells["code_freeze_days"]} |
| Go/No Go | {milestone_cells["go_no_go_date"]} | {milestone_cells["go_no_go_days"]} |
| GA Announce | {milestone_cells["ga_announce_date"]} | {milestone_cells["ga_announce_days"]} |

## Checks

| Check | Summary | Jira |
|---|---|---|
{_check_rows(report.get("results", []))}
"""


def enrich_report(report: dict) -> dict:
    """Attach formatted summaries and the fixed report template."""
    results = []
    for result in report.get("results", []):
        enriched = dict(result)
        enriched["summary"] = check_summary(result)
        enriched["teams"] = [
            {**team, "summary": check_summary(team)} for team in result.get("teams", [])
        ]
        results.append(enriched)

    enriched_report = dict(report)
    enriched_report["results"] = results
    enriched_report["report_markdown"] = render_report_markdown(
        {**enriched_report, "results": results}
    )
    return enriched_report
