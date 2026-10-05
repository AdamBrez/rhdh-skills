#!/usr/bin/env bash
#
# Multi-repo Yarn Berry 4.x bump: resolve version, clone, bump, open PR/MR.
# Mutator: bump-yarn.js. PR helper: midstream createPR.sh when CREATE_PR_SCRIPT is set.
#
#   yarn-bump.sh [--to VER] [--branch main] [--dry-run] [--no-push] [--workdir DIR]
#
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
BUMP_JS="${SCRIPT_DIR}/bump-yarn.js"
TOPIC="chore/automated-yarn-bump"
BOT_NAME="rhdh-bot service account"
BOT_EMAIL="rhdh-bot@redhat.com"

BRANCH="main"
TO=""
DRY_RUN=0
PUSH=1
WORKDIR=""
RC=0
GH_BIN_ROOT=""

GH_REPOS=(
  redhat-developer/rhdh-plugins
  redhat-developer/rhdh
  redhat-developer/rhdh-plugin-export-overlays
  redhat-developer/rhdh-cli
)
GL_REPOS=(
  rhidp/rhdh
  rhidp/rhdh-plugin-catalog
)

usage() {
  cat <<'EOF'
Usage:
  yarn-bump.sh [--to VER] [--branch main] [--dry-run] [--no-push] [--workdir DIR]

Resolves latest Yarn 4.x when --to is omitted. Clones GitHub then GitLab CEE,
runs bump-yarn.js --from-all (copies yarn-<to>.cjs into GL trees), commits as
rhdh-bot, opens PRs/MRs on chore/automated-yarn-bump.

Env: GITHUB_TOKEN or GH_TOKEN; PRIVATE_TOKEN (GitLab CEE);
     CREATE_PR_SCRIPT (path to createPR.sh, optional — falls back to gh/curl).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h | --help) usage; exit 0 ;;
    --to) TO="${2:?}"; shift 2 ;;
    --branch) BRANCH="${2:?}"; shift 2 ;;
    --workdir) WORKDIR="${2:?}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --no-push) PUSH=0; shift ;;
    *) echo "Unknown: $1" >&2; exit 1 ;;
  esac
done

for bin in node npm jq git; do
  command -v "$bin" >/dev/null || { echo "[ERROR] need ${bin}" >&2; exit 1; }
done
[[ -f "${BUMP_JS}" ]] || { echo "[ERROR] missing ${BUMP_JS}" >&2; exit 1; }

if [[ -n "${CREATE_PR_SCRIPT:-}" && -f "${CREATE_PR_SCRIPT}" ]]; then
  # shellcheck disable=SC1090
  source "${CREATE_PR_SCRIPT}"
fi

if [[ -z "${TO}" ]]; then
  TO=$(npm view @yarnpkg/cli versions --json \
    | jq -r '[.[] | select(test("^4\\.[0-9]+\\.[0-9]+$"))] | last')
  [[ -n "${TO}" && "${TO}" != "null" ]] || { echo "[ERROR] no Yarn 4.x on npm" >&2; exit 1; }
fi
echo "[INFO] yarn bump to=${TO} branch=${BRANCH}"

if [[ -z "${WORKDIR}" ]]; then
  WORKDIR=$(mktemp -d)
  trap 'rm -rf "${WORKDIR}"' EXIT
fi
mkdir -p "${WORKDIR}"

github_clone_url() {
  local slug="$1"
  local tok="${GITHUB_TOKEN:-${GH_TOKEN:-}}"
  if [[ -n "${tok}" ]]; then
    printf 'https://x-access-token:%s@github.com/%s.git' "${tok}" "${slug}"
  else
    printf 'https://github.com/%s.git' "${slug}"
  fi
}

gitlab_clone_url() {
  local slug="$1"
  local host="${CI_SERVER_HOST:-gitlab.cee.redhat.com}"
  local tok="${PRIVATE_TOKEN:-}"
  local user="${CI_PROJECT_NAME:-oauth2}"
  if [[ -n "${tok}" ]]; then
    printf 'https://%s:%s@%s/%s.git' "${user}" "${tok}" "${host}" "${slug}"
  else
    printf 'https://%s/%s.git' "${host}" "${slug}"
  fi
}

clone_repo() {
  local url="$1" dest="$2"
  git clone --branch "${BRANCH}" --single-branch --depth 50 "${url}" "${dest}"
  git -C "${dest}" config user.name "${BOT_NAME}"
  git -C "${dest}" config user.email "${BOT_EMAIL}"
}

has_open_gh_pr() {
  local dir="$1"
  command -v gh >/dev/null || return 1
  gh pr list --repo "$(git -C "${dir}" remote get-url origin | sed -E 's#.*github.com[:/](.+)(\.git)?$#\1#')" \
    --base "${BRANCH}" --state open --author rhdh-bot \
    --json headRefName,url 2>/dev/null \
    | jq -e --arg p "${TOPIC}" '[.[] | select(.headRefName | startswith($p))] | length > 0' >/dev/null
}

has_open_gl_mr() {
  local slug="$1"
  local tok="${PRIVATE_TOKEN:-}"
  local host="${CI_SERVER_HOST:-gitlab.cee.redhat.com}"
  [[ -n "${tok}" ]] || return 1
  local enc
  enc=$(printf '%s' "${slug}" | jq -sRr @uri)
  curl -fsS --header "PRIVATE-TOKEN: ${tok}" \
    "https://${host}/api/v4/projects/${enc}/merge_requests?state=opened&target_branch=${BRANCH}" \
    | jq -e --arg p "${TOPIC}" '[.[] | select(.source_branch | startswith($p))] | length > 0' >/dev/null
}

open_gitlab_mr() {
  local slug="$1" title="$2"
  local tok="${PRIVATE_TOKEN:-}"
  local host="${CI_SERVER_HOST:-gitlab.cee.redhat.com}"
  [[ -n "${tok}" ]] || { echo "[WARN] PRIVATE_TOKEN unset; no MR for ${slug}"; return 0; }
  local enc
  enc=$(printf '%s' "${slug}" | jq -sRr @uri)
  curl -fsS --request POST --header "PRIVATE-TOKEN: ${tok}" \
    --header "Content-Type: application/json" \
    --data "$(jq -n --arg s "${TOPIC}" --arg t "${BRANCH}" --arg title "${title}" \
      '{source_branch:$s,target_branch:$t,title:$title,remove_source_branch:true}')" \
    "https://${host}/api/v4/projects/${enc}/merge_requests" \
    | jq -r '.web_url // empty'
}

commit_and_pr() {
  local dir="$1" host="$2" slug="$3"
  local title="chore(deps): bump Yarn to ${TO}"
  pushd "${dir}" >/dev/null
  if [[ -z "$(git status --porcelain)" ]]; then
    echo "[INFO] ${slug}: no diff"
    popd >/dev/null
    return 0
  fi
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[INFO] dry-run: would commit/PR ${slug}"
    popd >/dev/null
    return 0
  fi
  git add -A
  git commit -s -m "$(printf 'chore(deps): bump Yarn to %s\n\nOpened by yarn-bump.sh (rhdh-yarn-bump skill).\n' "${TO}")"
  if [[ "${PUSH}" -eq 0 ]]; then
    echo "[INFO] ${slug}: committed, --no-push"
    popd >/dev/null
    return 0
  fi
  if [[ "${host}" == "github" ]] && declare -F createPr >/dev/null; then
    CREATE_PR_BODY="$(printf '## Summary\n- Bump Yarn Berry to `%s`.\n\n## Test plan\n- [ ] `yarn --version` is %s\n' "${TO}" "${TO}")"
    export CREATE_PR_BODY
    GITLAB_PIPELINE="${GITLAB_PIPELINE:-true}" createPr "${TOPIC}" "${BRANCH}" \
      --title "${title}" --body "${CREATE_PR_BODY}" || true
  elif [[ "${host}" == "github" ]]; then
    git checkout -B "${TOPIC}"
    git push -u origin "HEAD:${TOPIC}"
    gh pr create --base "${BRANCH}" --head "${TOPIC}" --title "${title}" \
      --body "$(printf 'Bump Yarn Berry to `%s`.\n' "${TO}")" --label ok-to-test 2>/dev/null \
      || gh pr create --base "${BRANCH}" --head "${TOPIC}" --title "${title}" \
        --body "$(printf 'Bump Yarn Berry to `%s`.\n' "${TO}")" || true
    gh pr comment --body "/ok-to-test" 2>/dev/null || true
  else
    git checkout -B "${TOPIC}"
    git push -u origin "HEAD:${TOPIC}"
    open_gitlab_mr "${slug}" "${title}" || true
  fi
  popd >/dev/null
}

process_gh() {
  local slug="$1"
  local name dest
  name=$(basename "${slug}")
  dest="${WORKDIR}/${name}"
  echo "=== ${slug} ==="
  if ! clone_repo "$(github_clone_url "${slug}")" "${dest}"; then
    echo "[ERROR] clone failed ${slug}"; RC=1; return
  fi
  if has_open_gh_pr "${dest}"; then
    echo "[INFO] skip ${slug}: open ${TOPIC}* PR"; return
  fi
  if ! node "${BUMP_JS}" --to "${TO}" --from-all --root "${dest}"; then
    echo "[ERROR] bump failed ${slug}"; RC=1; return
  fi
  if [[ -z "${GH_BIN_ROOT}" && -f "${dest}/.yarn/releases/yarn-${TO}.cjs" ]]; then
    GH_BIN_ROOT="${dest}"
  fi
  commit_and_pr "${dest}" github "${slug}" || RC=1
}

process_gl() {
  local slug="$1"
  local name dest
  name=$(basename "${slug}")
  dest="${WORKDIR}/gl-${name}"
  echo "=== gitlab ${slug} ==="
  if ! clone_repo "$(gitlab_clone_url "${slug}")" "${dest}"; then
    echo "[ERROR] clone failed ${slug}"; RC=1; return
  fi
  if has_open_gl_mr "${slug}"; then
    echo "[INFO] skip ${slug}: open ${TOPIC}* MR"; return
  fi
  local args=(--to "${TO}" --from-all --root "${dest}")
  if [[ -n "${GH_BIN_ROOT}" ]]; then
    args+=(--copy-bin "${GH_BIN_ROOT}")
  else
    echo "[WARN] no GH yarn-${TO}.cjs yet; GL bump may fail without binary"
  fi
  if ! node "${BUMP_JS}" "${args[@]}"; then
    echo "[ERROR] bump failed ${slug}"; RC=1; return
  fi
  commit_and_pr "${dest}" gitlab "${slug}" || RC=1
}

for slug in "${GH_REPOS[@]}"; do process_gh "${slug}"; done
for slug in "${GL_REPOS[@]}"; do process_gl "${slug}"; done

echo "[INFO] yarn-bump done (rc=${RC})"
exit "${RC}"
