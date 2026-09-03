# SoS release checks

This file is the runbook for the SoS release check-in report. Read **Query
vocabulary** first — it defines what each `Query` cell means. The **Schedule**
table below lists when each check runs and what it is called in the report.

Maintain the schedule table top to bottom. Section header rows name a milestone
gate; check rows beneath it run only while the release calendar is in that
section — a **Code Freeze** row never appears during the **Feature Freeze**
section, and vice versa. On each run the CLI resolves `When` against
`/rhdh-release-schedule` milestone dates, executes every check whose resolved
date is on or before today, and stops before the first future check in the
active section. Upcoming checks are not rendered in the report.

## Query vocabulary

Every check row ends in a Jira query. The query decides **what** is counted; the
`When` column decides **when** that row appears in the report.

| Query | What Jira counts | When to use it |
|---|---|---|
| `static "Name"` | The Rich Filter static filter **Name**, scoped to this release (`fixVersion`) | A **count** or **snapshot** — especially when you need `+ extra JQL` to narrow the scope |
| `static "Name" + …` | Same static filter, plus extra JQL after `+` | A **slice** of that scope (e.g. not in a sprint, wrong status) |
| `due static "Name"` | **The same JQL as** bare `static "Name"` — full filter, no extras | **Due by milestone** **Name** — tracked from early in the section through that milestone day |
| `expect assignee summary ~ "pattern"` | Open issues whose summary contains **pattern**, scoped to this release | A **named ticket must exist and have an assignee** — pass/fail, not a volume count |
| `expect assignee summary ~ "pattern" + …` | Same, plus extra JQL after `+` | Narrow to one ticket shape (e.g. `issuetype = Epic`) |
| `metric epic_dev_complete static "Name"` | Epics under static filter **Name**; reports % in Dev Complete | Epic readiness before Feature Freeze |
| `template blockers` | Named template from the Rich Filter overlay | Blocker bugs (and similar template-backed scopes) |
| `queue "RNs Unclassified"` | Named Rich Filter queue + `fixVersion` | Queue-backed scopes such as release notes |

### `static` vs `due static` — same number, different job

These two look similar in the vocabulary table. The difference is **not** a
different Jira filter — for the same name (e.g. `"Feature Freeze"`), both count
issues in that static filter for the release.

| | `static "Feature Freeze"` | `due static "Feature Freeze"` |
|---|---|---|
| Jira scope | Rich Filter **Feature Freeze** + `fixVersion` | **Identical** |
| Extra JQL | Yes — `+ sprint is EMPTY`, `+ status in (…)`, etc. | No — always the full filter |
| Report role | Count check or **milestone snapshot** (see row title) | **Due by Feature Freeze** — scope that should clear by that date |
| HTML | Count, team breakdown, Jira link | Same, plus **Complete by Feature Freeze · `<date>`** |
| After Feature Freeze day | Row can still appear if its `When` date is due (e.g. FF - 0d snapshot) | Row is **dropped** — due-by tracking ends on the milestone |

**Rule of thumb:** use `due static` once per milestone for “how much scope must
clear by this gate?” Use `static` for snapshots, slices, and anything that needs
`+ extra JQL`. Do not add a second row that repeats bare `static "Feature Freeze"`
or `static "Code Freeze"` mid-section — the `due static` row already tracks that
full scope from the first offset in the section.

Supported names for `due static` today: **Feature Freeze**, **Code Freeze**.

### `expect assignee` — one ticket, must have an owner

Use when the check is about **a specific coordination ticket**, not how many issues
are open in a filter.

| Query part | Meaning |
|---|---|
| `expect assignee` | Check kind — verify assignee on a matching ticket |
| `summary ~ "pattern"` | Jira `summary ~ "pattern"` (contains, case-sensitive in Jira) plus `fixVersion` |
| `+ …` | Optional extra JQL after `+` (e.g. `issuetype = Epic`) |

Report summaries:

| Summary | Meaning |
|---|---|
| `Assigned (RHIDP-123)` | Exactly one match, assignee set — green |
| `Unassigned — find an owner` | One match, no assignee — action needed |
| `Not found — create or link ticket` | No open issue matches — action needed |
| `Multiple matches (KEY-1, KEY-2) — pick one ticket` | Pattern matched more than one issue — action needed |

The Jira column links to the ticket when there is a single match; otherwise it
links to the search. No team breakdown — this is not team-scoped volume.

Pick a **distinct enough** `summary ~` pattern so only the intended ticket matches.
Add more checks by adding rows with different patterns.

## Check notes

- **Epic Dev Complete** (`metric epic_dev_complete static "Feature Freeze"`) uses
  the static **Feature Freeze** filter scoped to `issuetype = Epic`. The exported
  filter's `status not in (…)` clause is dropped for the denominator so Dev
  Complete epics count in the total. Runs from **FF - 21d** through **Feature
  Freeze day** only.
- **Due by milestone** (`due static "…"`) uses the matching static filter as-is,
  starts at the first offset shown in the schedule, shows the milestone date as
  the completion target in HTML, includes team breakdown, and stops after that
  milestone day.
- **Expect assignee** (`expect assignee summary ~ "…"`) finds open issues matching
  the summary pattern and release `fixVersion`. Exactly one match with an assignee
  passes; zero, many, or unassigned matches call for action in the summary.

## Schedule

| When | Check | Query |
|------|-------|-------|
| Feature Freeze | | |
| FF - 21d | FF Epics, Stories, Tasks not in a sprint | static "Feature Freeze" + sprint is EMPTY |
| FF - 21d | FF Epics, Stories, Tasks in New, To Do, or Backlog | static "Feature Freeze" + status in (New, "To Do", Backlog) |
| FF - 21d | FF Epics Dev Complete | metric epic_dev_complete static "Feature Freeze" |
| FF - 21d | Work remaining for Feature Freeze | due static "Feature Freeze" |
| FF - 21d | Test Day ticket has owner | expect assignee summary ~ "Test Day" + issuetype = Epic |
| FF - 0d | Feature Freeze day snapshot | static "Feature Freeze" |
| Code Freeze | | |
| CF - 14d | Blocker bugs outstanding | template blockers |
| CF - 14d | CF work remaining for Code Freeze | due static "Code Freeze" |
| CF - 0d | Code Freeze day snapshot | static "Code Freeze" |
| Go/No Go | | |
| GNG - 7d | Open engineering EPICs | template epics |
| GNG - 7d | Unclassified release notes | queue "RNs Unclassified" |
| GA Announce | | |
| GA - 7d | Post Code Freeze scope | template post_code_freeze_issues |
