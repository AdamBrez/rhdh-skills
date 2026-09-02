# SoS release checks

Maintain this table top to bottom. Section header rows name a milestone gate; check
rows beneath it run only while the release calendar is in that section. On each run
the CLI resolves `When` against `/rhdh-release-schedule` milestone dates, executes
every check whose resolved date is on or before today, and stops before the first
future check in the active section.

Query vocabulary:

| Query | Meaning |
|---|---|
| `static "Feature Freeze"` | Rich Filter static filter + fixVersion |
| `static "Feature Freeze" + sprint is EMPTY` | static filter composed with extra JQL |
| `template blockers` | Named template from `jql-release.md` / Rich Filter overlay |
| `queue "RNs Unclassified"` | Rich Filter queue + fixVersion |

| When | Check | Query |
|------|-------|-------|
| Feature Freeze | | |
| FF - 21d | FF Epics, Stories, Tasks not in a sprint | static "Feature Freeze" + sprint is EMPTY |
| FF - 21d | FF Epics, Stories, Tasks in New, To Do, or Backlog | static "Feature Freeze" + status in (New, "To Do", Backlog) |
| FF - 7d | FF scope outstanding | static "Feature Freeze" |
| FF - 0d | Feature Freeze day snapshot | static "Feature Freeze" |
| Code Freeze | | |
| CF - 14d | Blocker bugs outstanding | template blockers |
| CF - 7d | Code Freeze scope outstanding | static "Code Freeze" |
| CF - 0d | Code Freeze day snapshot | static "Code Freeze" |
| Go/No Go | | |
| GNG - 7d | Open engineering EPICs | template epics |
| GNG - 7d | Unclassified release notes | queue "RNs Unclassified" |
| GA Announce | | |
| GA - 7d | Post Code Freeze scope | template post_code_freeze_issues |
