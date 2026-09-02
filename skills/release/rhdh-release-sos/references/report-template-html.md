# SoS HTML report template

The CLI renders a self-contained HTML page from the same report data as
`report_markdown`. Embedded CSS only — no external assets or JavaScript.

## Structure

1. Header — title and metadata (`As of`, `Release phase`, `Next milestone`)
2. Milestones — table; highlight the active release phase row
3. Checks — table with check rows and indented team sub-rows
4. Footer — generation date

Summary badges use the same values as markdown: `None open`, `1 open`, `N open`,
`Unverified`, with color coding (green / amber / gray).

## CLI output

`run` always writes the HTML file and returns:

- `report_markdown` — show unchanged in chat
- `report_html` — full page source (JSON only; do not paste into chat)
- `report_html_path` — absolute path to the written file for download or publishing

Default file name when `--html-output` is omitted:
`reports/rhdh-{version}-sos-{as-of}.html` under this skill directory.

The workflow passes `--html-output reports/rhdh-{version}-sos.html` so the path is
stable and easy to find. Override `--html-output` when the user wants the file
somewhere else.

The CLI prints `SOS_HTML_REPORT=<path>` on stderr even with `--json`.

Present `report_markdown` in the conversation and give the user the absolute
`report_html_path` so they can open, attach, or publish the HTML file. Do not
complete the skill run unless that file exists on disk.
