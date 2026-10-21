---
name: rhdh-plugin-catalog-index-status-and-update-flow
description: >-
  Reports Red Hat Developer Hub plugin catalog index status for a release
  branch or x.y.z and updates the downstream quay.io/rhdh/plugin-catalog-index
  after you approve the push. Reads the upstream Plugin-Catalog-Status wiki and
  midstream docs/catalog-status.md, classifies missing Quay tags into Konflux
  respins versus sync-midstream calls to action, and waits on rhdh-tenant
  PipelineRuns with oc. Use for "catalog index status", "plugin catalog index
  is failing", "missing plugin builds", "outdated workspaces", "update the
  downstream catalog index", "quay.io/rhdh/plugin-catalog-index",
  "checkPluginsExist", or "Konflux plugin PipelineRuns".
compatibility: >-
  Python 3.9+, git, oc logged into the Konflux stone-prod-p02 cluster, and an
  rhdh-plugin-catalog worktree. skopeo is used only when confirming Quay tags
  after a build.
---

# Plugin catalog index status and update

Bring one release's downstream plugin catalog index current, and say what is still blocked. Supported plugins only. The index this skill publishes is `quay.io/rhdh/plugin-catalog-index`.

Run `scripts/catalog_index_status.py` by path. It prints JSON and does not prompt, commit, or push.

## Gate

Run `check-login` before resolving a version, fetching status, or touching git. A refused login stops the skill. Load `references/konflux-wait.md` and wait until the user has an `oc` session.

## Resolve

Ask for `x.y.z` or a branch (`main`, `release-2.1`) when the user named neither. Then:

```bash
python3 scripts/catalog_index_status.py resolve --branch <branch> --version <x.y.z> --catalog-root <worktree>
```

Pass whichever half the user gave. The script reads `version` from `redhat-developer/rhdh` `package.json` on that branch, and uses `release-X.Y` when that catalog branch exists, otherwise `main`.

Use a git worktree of `gitlab.cee.redhat.com:rhidp/rhdh-plugin-catalog` on the resolved branch. Clone the repo when it is not on disk. Leave the user's current checkout where it is.

## Report

```bash
python3 scripts/catalog_index_status.py report \
  --catalog-root <worktree> \
  --downstream <worktree>/docs/catalog-status.md \
  --branch <branch> \
  --version <x.y.z>
```

Load `references/status-pages.md` to act on the JSON.

- Respin rows: run each `command` from the worktree. That commits `.tekton/` PipelineRuns and does not push.
- Sync rows: show `syncCommand` and stop. Running `sync-midstream.sh` is a later session.
- Report-only rows: include them in the summary. They do not start a Konflux build.

## Push

Invoke `/mutation-gate` before `git push` of the catalog branch. Name the branch, show `git status` and `git diff --cached`, and say that a pushed PipelineRun commit cannot be undone because Konflux starts the build. The user's request to inspect status does not approve the push.

After an authorized push, open `konfluxUrl` and run `wait-runs` from `references/konflux-wait.md`. Then confirm the requested tags with `skopeo inspect docker://<ref>`. Still missing, failed, or timed out: report the Konflux link, the Quay links, and `syncCommand` when workspaces are behind.

When respin and sync are both empty, ask before `./build/ci/update-index.sh` with the `indexFlags` from `resolve` and `--nopush`. Ask separately, default no, for `--allow-fallback-tag` and `--allow-version-regression`. Push that commit only through another `/mutation-gate` approval. `/mutation-gate` returns the approved operation list; run only that list.

## Completion

The user has a JSON report for the branch, any local commits are unpushed unless a gate approval pushed them, PipelineRun reasons are `Succeeded` or an explicit failure with log paths, and the downstream index command was either skipped or run with `--nopush` until a second approval.
