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

## Completion

Show `report_markdown` exactly as returned. Every due check row must keep its Jira
link from the CLI.
