"""Render SoS check-in reports from a fixed template."""

from __future__ import annotations

from html import escape

import sos_metrics as metrics_mod

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
    if result.get("kind") == "expect_assignee":
        if result.get("status") == "unverified":
            return "Unverified"
        return str(result.get("summary", "Unverified"))

    if result.get("kind") == "ratio":
        return metrics_mod.ratio_summary(
            result.get("numerator"),
            result.get("denominator"),
            status=result.get("status", "ok"),
        )

    if result.get("status") == "unverified":
        return "Unverified"

    count = result.get("count")
    if count == 0:
        return "None open"
    if count == 1:
        return "1 open"
    return f"{count} open"


def summary_css_class(result: dict) -> str:
    """CSS class for a check or team summary badge."""
    if result.get("status") == "unverified":
        return "summary-unverified"
    if result.get("kind") == "expect_assignee":
        if result.get("expect_state") == "assigned":
            return "summary-none"
        return "summary-open"
    if result.get("kind") == "ratio":
        denominator = result.get("denominator")
        if not denominator:
            return "summary-none"
        if result.get("percent") == 100:
            return "summary-none"
        return "summary-open"
    count = result.get("count")
    if count == 0:
        return "summary-none"
    return "summary-open"


def _html_jira_link(url: str | None, label: str = "Open in Jira") -> str:
    if not url:
        return "—"
    safe_url = escape(url, quote=True)
    safe_label = escape(label)
    return (
        f'<a class="jira-link" href="{safe_url}" target="_blank" '
        f'rel="noopener noreferrer">{safe_label}</a>'
    )


def _html_summary_badge(result: dict) -> str:
    summary = check_summary(result)
    css_class = summary_css_class(result)
    return f'<span class="summary {css_class}">{escape(summary)}</span>'


def _html_team_breakdown_block(result: dict) -> str:
    teams = result.get("teams", [])
    if not teams:
        return ""
    team_count = len(teams)
    label = "team" if team_count == 1 else "teams"
    body = f"""
        <table class="team-table">
          <thead>
            <tr>
              <th>Team</th>
              <th>Summary</th>
              <th>Jira</th>
            </tr>
          </thead>
          <tbody>
            {_html_team_table_rows(teams)}
          </tbody>
        </table>"""

    return f"""
      <details class="team-breakdown">
        <summary>Team breakdown ({team_count} {label})</summary>
        {body}
      </details>"""


def _html_check_due_line(result: dict) -> str:
    if result.get("kind") != "due":
        return ""
    due_date = result.get("due_by_date", "TBD")
    milestone = result.get("due_by_milestone", "Feature Freeze")
    return f'<div class="check-due">Complete by {escape(milestone)} · {escape(str(due_date))}</div>'


def _html_team_table_rows(teams: list[dict]) -> str:
    rows: list[str] = []
    for team in teams:
        label = team_display_name(team["team_name"])
        rows.append(
            "<tr>"
            f"<td>{escape(label)}</td>"
            f"<td>{_html_summary_badge(team)}</td>"
            f"<td>{_html_jira_link(team.get('jira_url'))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _html_checks_section(results: list[dict]) -> str:
    if not results:
        return '<p class="checks-empty"><em>No checks due today.</em></p>'

    blocks: list[str] = []
    for result in results:
        teams = result.get("teams", [])
        team_markup = _html_team_breakdown_block(result) if teams else ""
        block_class = "check-block has-teams" if teams else "check-block"
        jira_link = _html_jira_link(
            result.get("issue_url") or result.get("jira_url"),
            label=result.get("issue_key") or "Open in Jira",
        )
        blocks.append(
            f"""
    <article class="{block_class}">
      <div class="check-row">
        <div class="check-title">{escape(result["title"])}{_html_check_due_line(result)}</div>
        <div class="check-summary">{_html_summary_badge(result)}</div>
        <div class="check-jira">{jira_link}</div>
      </div>{team_markup}
    </article>"""
        )

    return f"""
      <div class="checks-head">
        <div>Check</div>
        <div>Summary</div>
        <div>Jira</div>
      </div>
      <div class="checks-list">{"".join(blocks)}
      </div>"""


def _html_milestone_rows(report: dict) -> str:
    active_key = report.get("active_section", {}).get("milestone_key", "")
    rows: list[str] = []
    for key, label in _MILESTONE_ORDER:
        milestone = next(
            (item for item in report.get("milestones", []) if item["key"] == key), None
        )
        if milestone is None:
            date = "TBD"
            days = "TBD"
        else:
            date = str(milestone.get("date", "TBD"))
            days_value = milestone.get("days_until")
            days = str(days_value) if days_value is not None else "TBD"
        row_class = ' class="milestone-active"' if key == active_key else ""
        rows.append(
            f"<tr{row_class}>"
            f"<td>{escape(label)}</td>"
            f"<td>{escape(date)}</td>"
            f'<td class="num">{escape(days)}</td>'
            "</tr>"
        )
    return "\n".join(rows)


_HTML_STYLES = """
:root {
  color-scheme: light;
  --bg: #f4f4f5;
  --surface: #ffffff;
  --text: #151515;
  --muted: #5c5c5c;
  --border: #d9d9de;
  --accent: #ee0000;
  --summary-none-bg: #e8f5e9;
  --summary-none-text: #1b5e20;
  --summary-open-bg: #fff3e0;
  --summary-open-text: #e65100;
  --summary-unverified-bg: #eceff1;
  --summary-unverified-text: #455a64;
  --milestone-active-bg: #fff5f5;
  --check-row-bg: #eef3fb;
  --check-row-border: #c8d6ef;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 2rem 1rem 3rem;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.5;
  color: var(--text);
  background: var(--bg);
}
.page {
  max-width: 960px;
  margin: 0 auto;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.06);
  overflow: hidden;
}
header {
  padding: 1.75rem 2rem 1.25rem;
  border-bottom: 3px solid var(--accent);
}
header h1 {
  margin: 0 0 1rem;
  font-size: 1.6rem;
  line-height: 1.25;
}
.meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.75rem 1.5rem;
}
.meta dt {
  margin: 0;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--muted);
}
.meta dd {
  margin: 0.15rem 0 0;
  font-size: 0.98rem;
}
section {
  padding: 1.25rem 2rem 1.75rem;
}
section + section {
  border-top: 1px solid var(--border);
}
section h2 {
  margin: 0 0 1rem;
  font-size: 1.1rem;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.95rem;
}
th, td {
  padding: 0.65rem 0.75rem;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}
th {
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--muted);
  background: #fafafa;
}
td.num, th.num { text-align: right; }
tr.milestone-active td {
  background: var(--milestone-active-bg);
  font-weight: 600;
}
.checks-head,
.check-row {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(8rem, 0.7fr) minmax(7rem, 0.55fr);
  gap: 0.75rem;
  align-items: center;
}
.checks-head {
  padding: 0 0.75rem 0.5rem;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--muted);
}
.checks-list {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}
.check-block {
  border: 1px solid var(--check-row-border);
  border-radius: 10px;
  overflow: hidden;
  background: var(--surface);
}
.check-row {
  padding: 0.8rem 0.75rem;
  background: var(--check-row-bg);
  font-weight: 700;
}
.check-title {
  font-weight: 700;
  color: var(--text);
}
.check-due {
  margin-top: 0.2rem;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--muted);
}
.team-breakdown {
  border-top: 1px solid var(--check-row-border);
  background: #fafbfd;
}
.team-breakdown > summary {
  cursor: pointer;
  list-style: none;
  padding: 0.55rem 0.75rem;
  font-size: 0.84rem;
  font-weight: 600;
  color: var(--muted);
  background: #f6f8fc;
}
.team-breakdown > summary::-webkit-details-marker {
  display: none;
}
.team-breakdown > summary::before {
  content: "▸";
  display: inline-block;
  width: 1rem;
  color: var(--muted);
}
.team-breakdown[open] > summary::before {
  content: "▾";
}
.team-breakdown[open] > summary {
  border-bottom: 1px solid var(--border);
}
.team-table {
  width: 100%;
  margin: 0;
  font-size: 0.92rem;
}
.team-table th,
.team-table td {
  padding: 0.55rem 0.75rem;
}
.team-table th {
  background: #f3f5f8;
}
.check-summary,
.check-jira {
  font-weight: 600;
}
.checks-empty {
  margin: 0;
  color: var(--muted);
}
.summary {
  display: inline-block;
  padding: 0.15rem 0.55rem;
  border-radius: 999px;
  font-size: 0.82rem;
  font-weight: 600;
  white-space: nowrap;
}
.summary-none {
  background: var(--summary-none-bg);
  color: var(--summary-none-text);
}
.summary-open {
  background: var(--summary-open-bg);
  color: var(--summary-open-text);
}
.summary-unverified {
  background: var(--summary-unverified-bg);
  color: var(--summary-unverified-text);
}
.jira-link {
  color: #0066cc;
  text-decoration: none;
  font-weight: 600;
}
.jira-link:hover { text-decoration: underline; }
footer {
  padding: 1rem 2rem 1.5rem;
  border-top: 1px solid var(--border);
  font-size: 0.82rem;
  color: var(--muted);
  background: #fafafa;
}
@media print {
  body { background: white; padding: 0; }
  .page { box-shadow: none; border: none; }
  .jira-link { color: inherit; text-decoration: underline; }
  .team-breakdown > summary { display: none; }
  .team-breakdown .team-table { display: table; }
}
"""


def render_report_html(report: dict) -> str:
    """Render a self-contained HTML page for the SoS report."""
    version = escape(report["version"])
    as_of = escape(report["as_of"])
    section = escape(report["active_section"]["title"])
    next_milestone = escape(_next_milestone_line(report))
    title = f"RHDH {version} — SoS Release Check-in"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>{_HTML_STYLES}</style>
</head>
<body>
  <main class="page">
    <header>
      <h1>{title}</h1>
      <dl class="meta">
        <div><dt>As of</dt><dd>{as_of}</dd></div>
        <div><dt>Release phase</dt><dd>{section}</dd></div>
        <div><dt>Next milestone</dt><dd>{next_milestone}</dd></div>
      </dl>
    </header>
    <section>
      <h2>Milestones</h2>
      <table>
        <thead>
          <tr>
            <th>Milestone</th>
            <th>Date</th>
            <th class="num">Days remaining</th>
          </tr>
        </thead>
        <tbody>
          {_html_milestone_rows(report)}
        </tbody>
      </table>
    </section>
    <section>
      <h2>Checks</h2>
      {_html_checks_section(report.get("results", []))}
    </section>
    <footer>Generated {as_of} · RHDH release SoS check-in</footer>
  </main>
</body>
</html>
"""


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


def _result_jira_cell(result: dict) -> str:
    key = result.get("issue_key")
    url = result.get("issue_url") or result.get("jira_url")
    if key and url:
        return f"[{key}]({url})"
    return _jira_cell(url)


def _check_rows(results: list[dict]) -> str:
    if not results:
        return "| _No checks due today._ | | |"
    lines = []
    for result in results:
        lines.append(
            f"| {result['title']} | {check_summary(result)} | {_result_jira_cell(result)} |"
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
{_check_rows(report.get("results", []))}"""


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
    enriched_report["report_html"] = render_report_html({**enriched_report, "results": results})
    return enriched_report
