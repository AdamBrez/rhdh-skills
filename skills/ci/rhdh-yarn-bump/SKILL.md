---
name: rhdh-yarn-bump
description: >-
  Bumps Yarn Berry across the RHDH repos — rhdh-plugins, rhdh midstream,
  rhdh-plugin-export-overlays, rhdh-cli, and GitLab CEE rhidp/rhdh and
  rhdh-plugin-catalog — with `yarn set version` plus install, and rewrites the
  pins Yarn cannot see: `packageManager`, `yarnPath`, `ENV YARN=`, and
  Containerfile lines. Use for "bump yarn to 4.17.1", "upgrade Yarn Berry across
  the repos", "weekly yarn bump", "which Yarn version is each repo pinned to",
  or scanning yarn pins.
compatibility: "Node, yarn, git, gh on PATH; PRIVATE_TOKEN + gitlab.cee.redhat.com for GitLab CEE MRs."
---

# RHDH multi-repo Yarn bump

## Goal

Propagate a Yarn Berry 4.x bump across:

| Repo | Notes |
| --- | --- |
| [`redhat-developer/rhdh-plugins`](https://github.com/redhat-developer/rhdh-plugins) | root workspace (+ Fullsend if hardcoded) |
| [`redhat-developer/rhdh`](https://github.com/redhat-developer/rhdh) | root + nested workspaces + Containerfile |
| [`redhat-developer/rhdh-plugin-export-overlays`](https://github.com/redhat-developer/rhdh-plugin-export-overlays) | many `packageManager` pins |
| [`redhat-developer/rhdh-cli`](https://github.com/redhat-developer/rhdh-cli) | root `packageManager` / `yarnPath` |
| [`gitlab.cee.redhat.com/rhidp/rhdh`](https://gitlab.cee.redhat.com/rhidp/rhdh) | distgit binary + `ENV YARN=` (copy binary from GH bump) |
| [`gitlab.cee.redhat.com/rhidp/rhdh-plugin-catalog`](https://gitlab.cee.redhat.com/rhidp/rhdh-plugin-catalog) | per-workspace pins + Containerfiles |

Renovate Yarn `packageManager` updates are disabled (RHIDP-17563). This skill is the bump path.

**Branch:** live line is `main` on GitHub and GitLab CEE. Extra `release-2.*` lines are a future weekly-maintenance loop, not a second flag.

## Default path: weekly script

The product is the script. Weekly CI and humans run the same command:

```bash
SKILL=<this skill's directory>
node "$SKILL/scripts/weekly-yarn-bump.js"          # resolve latest Yarn 4.x, clone, bump, PR/MR
node "$SKILL/scripts/weekly-yarn-bump.js" --to 4.18.1 --dry-run
node "$SKILL/scripts/weekly-yarn-bump.js" --help
```

It:

1. Resolves latest **Yarn 4.x** (`@yarnpkg/cli`; never `stable`, never 5.x unless `--to` is exact).
2. Clones `main` for the six repos (GitHub first).
3. Skips a repo if it is already on `--to`, only denylist pins remain (`4.8.1` / `4.9.2` / `4.15.0`), or an open bot PR/MR exists on `chore/automated-yarn-bump*`.
4. Runs `yarn set version` on GitHub; **copies** `yarn-<to>.cjs` into GitLab CEE trees (no extra download).
5. Rewrites extras (`ENV YARN=`, Containerfile, embedded `yarn set version`) and refreshes lockfiles in the **same** run.
6. Commits as `rhdh-bot`, pushes, opens GitHub PRs (`ok-to-test`) / GitLab CEE MRs. No Jira. `--no-open`.

`--from` in weekly mode is every non-denylist pin that is not already `--to`.

Lock refresh for overlays / rhdh-plugins can exceed **45 minutes**. Failures in one repo do not skip the rest; the process exits non-zero if any repo failed.

GitLab weekly-maintenance clones this skill and runs the script **once** after digest/bootc work and **before** Quay tag deletion. Extra branches later: one `--branch` loop in that shell, not a second yarn phase.

## Manual mutator (existing checkouts)

When trees are already cloned:

```bash
node "$SKILL/scripts/bump-yarn.js" --scan --root /path/to/repo
node "$SKILL/scripts/bump-yarn.js" --to 4.18.1 --from-all --root /path/to/rhdh-plugins
node "$SKILL/scripts/bump-yarn.js" --to 4.18.1 --copy-bin /path/to/rhdh-plugins \
  --from-all --root /path/to/rhdh-downstream
```

`--from 4.12.0,4.14.1` remains the human default when `--from-all` is omitted.

## Anti-patterns

- Do not re-enable Renovate Yarn bumps; they only update one repo and miss Containerfile / `ENV YARN=`.
- Do not `yarn set version stable` — repos must share one exact 4.x.
- Do not download a second Yarn binary for GitLab CEE; copy the GitHub `yarn-<to>.cjs`.
- Do not special-case `rhdh-1-rhel-9`; both CEE repos default to `main`.

## Tests

```bash
node --test "$SKILL/tests/bump-yarn.test.mjs"
```

## Completion

Weekly/CI is done when each requested repo was processed and stdout lists `repo:` / `skipped:` / `url:` lines. A bump on a root is done when matching workspaces sit on `--to` (`packageManager`, `yarnPath`, `yarn-<to>.cjs` mode `100755`), extras are rewritten, and lockfiles refreshed unless `--no-refresh-locks`.
