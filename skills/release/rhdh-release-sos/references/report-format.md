# SoS report format

Present the CLI `report_markdown` field unchanged. The layout is fixed in
`references/report-template.md` and rendered by `scripts/sos_report_format.py`.

## Sections (always this order)

1. Title and metadata table — as-of date, release phase, next milestone
2. Milestones — four rows: Feature Freeze, Code Freeze, Go/No Go, GA Announce
3. Checks — one row per due check with summary and `[Open in Jira](url)`, then one
   sub-row per engineering team (`↳ Team name`) with the same check scoped to that
   team and its own Jira link

Do not add upcoming checks, follow-up bullet lists, executive narrative, or runbook
execution metadata.

## Check row summaries

Use the CLI `results[].summary` value only:

| Summary | Meaning |
|---|---|
| `None open` | Count is 0 |
| `1 open` | Count is 1 |
| `N open` | Count is greater than 1 |
| `Unverified` | Jira count failed |
| `None` | Ratio check with zero Epics in scope |
| `N% (numerator/denominator)` | Epic Dev Complete ratio |
| `Assigned (KEY)` | Expect assignee — one match with an owner |
| `Unassigned — find an owner` | Expect assignee — match exists, no assignee |
| `Not found — create or link ticket` | Expect assignee — no matching open issue |
| `Multiple matches (…)` | Expect assignee — pattern matched more than one issue |

## Completion

Show `report_markdown` exactly as returned in the conversation. Every due check row
must keep its Jira link from the CLI.

Also give the user the absolute `report_html_path` from the CLI JSON so they can
download or publish the self-contained HTML page. The file must exist on disk before
the run is complete. Do not paste `report_html` into chat unless the user explicitly
asks for the source.
