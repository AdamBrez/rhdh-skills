# Konflux login and wait

Load this when `check-login` fails or after an authorized push.

## Login

`check-login` runs `oc whoami` and refuses the same way `build/scripts/kfuxRelease.sh` does: a non-zero exit, or output that contains `You must be logged in`, `cannot get resource`, `Error`, or `Forbidden`.

Stop the skill until the user logs in:

```bash
oc login --server=https://api.stone-prod-p02.hjvn.p1.openshiftapps.com:6443
```

The token comes from the `rhdh-tenant` console page linked in the script's `loginHint` (username, Copy login command, Display token). Do not continue to resolve, fetch, or git while login is refused.

## Watch

After the user authorizes a push, record an RFC3339 timestamp and run one blocking command:

```bash
python3 scripts/catalog_index_status.py wait-runs \
  --application <application from resolve> \
  --since <timestamp>
```

The application name is the `appstudio.openshift.io/application` value on `.tekton/plugin-catalog-index-*-push.yaml` (`rhdh-plugin-catalog-2` on current `main`). Open `konfluxUrl` in the browser for the human.

The command follows each new PipelineRun in `rhdh-tenant` with `oc logs -f` into a temp file until the Succeeded condition is terminal. If the live object is gone, it reads `pipelineruns.kubearchive.org`. Do not start a five-minute agent loop.

A run that is still missing when `--appear-timeout` ends, or whose reason is not `Succeeded`, is unresolved. Report the Konflux link, the Quay tag links from the status page, and `actions.syncCommand` when workspaces are behind.
