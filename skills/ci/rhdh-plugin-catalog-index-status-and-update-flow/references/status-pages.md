# Status pages

Load this when classifying a release after `report` prints JSON.

## Sources

| Page | What it covers |
| --- | --- |
| GitHub wiki `Plugin-Catalog-Status-<branch>` | Upstream Supported and Community catalogs built on GitHub. Example page title for `main`: `Plugin-Catalog-Status-main`. |
| `docs/catalog-status.md` in the catalog worktree | Downstream Supported catalog built in Konflux. |

The script reads both. Upstream rows are report-only. A Konflux respin does not fix a GitHub-built catalog.

## Actions

`scripts/catalog_index_status.py report` splits downstream rows:

- **respin** — Failed or Outdated, the requested plugin version is already in that workspace's `package.json`, and the script prints the `.tekton/updatePLRs.sh -v <x.y.z> --trigger --path <path> --nopush` command. `--path` matches a line in `overlay-repo/rhdh-supported-packages.txt`. The script appends `$` itself; do not add another one.
- **sync** — the workspace is missing or its `package.json` version differs from the requested plugin version. Print `actions.syncCommand` and stop. Do not run `sync-midstream.sh`.
- **reportOnly** — downstream Backstage mismatches, plus every upstream failed, outdated, and mismatch row.

Supported plugins only. Do not pass `--community` to `updatePLRs.sh`.

## Downstream index

When the report has no respin and no sync rows, ask before:

```bash
./build/ci/update-index.sh <indexFlags from resolve> --nopush
```

That updates `quay.io/rhdh/plugin-catalog-index` only. `indexFlags` is `--next` on `main`, `--overlays-branch <release> --latest` on the highest `release-X.Y`, and `--overlays-branch <release>` on older release branches. Do not pass `--community-registry`. Ask separately, default no, before adding `--allow-fallback-tag` or `--allow-version-regression`. Add `--rhec` only when the user asks to publish `registry.access.redhat.com/rhdh` refs.
