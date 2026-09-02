# Workflow: SoS release check-in

Build the cumulative Scrum of Scrums release report from `references/sos-checks.md`.

<prerequisites>

Run `uv run scripts/sos_report.py --json check` and require the Rich Filter contract
check to pass. `references/config.md` documents the shared export with
`/rhdh-release-status`. When Jira or the export is unavailable, name what stayed
unverified rather than guessing counts.

</prerequisites>

<process>

## Step 1: Resolve the release version

Ask when the request omits a version. Do not default to the newest release you have
seen elsewhere in the conversation.

## Step 2: Confirm milestone dates

Invoke `/rhdh-release-schedule` for the same version when the CLI cannot find an
active Jira release issue, or when the user asks to reconcile dates. The SoS CLI
reads active-release milestone dates from Jira directly.

## Step 3: Run the check-in CLI

```bash
uv run scripts/sos_report.py --json run {{VERSION}}
```

Use `--date YYYY-MM-DD` only when the user names an as-of date other than today.
Use `plan` instead of `run` when the user wants due checks listed without Jira
counts.

The cumulative rule is implemented in the CLI: within the active milestone section,
every check whose resolved date is on or before today runs. See
`references/timeline.md`.

## Step 4: Present the report

Show `report_markdown` exactly as the CLI returns it. The fixed layout is defined
in `references/report-template.md`. Do not add upcoming checks, follow-up lists,
runbook execution counts, or extra narrative around the template.

</process>

<gotchas>

- Section headers in `sos-checks.md` are not checks. Only rows with a **Check** and
  **Query** column execute.
- Feature Freeze filter scope excludes bugs and Features by design.
- Checks in a later milestone section never run early.
- Never paraphrase check summaries or rebuild the Checks table by hand.

</gotchas>

<success_criteria>

- [ ] `report_markdown` is shown unchanged from the CLI
- [ ] Every due check row has a summary and `[Open in Jira](url)` link
- [ ] Every due check includes team sub-rows with summary and Jira link where Cloud ID exists
- [ ] No upcoming-checks section and no runbook execution metadata were added
- [ ] Nothing was posted

</success_criteria>
