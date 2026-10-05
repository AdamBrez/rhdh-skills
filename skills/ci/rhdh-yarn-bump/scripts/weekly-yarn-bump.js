#!/usr/bin/env node
/**
 * Unattended Yarn 4.x bump for weekly-maintenance and local CI.
 *
 * Clones GitHub + GitLab CEE `main`, skips denylist / open bot PRs, bumps GH
 * first then copies yarn-<to>.cjs into GitLab trees, refreshes locks, opens
 * PRs/MRs on chore/automated-yarn-bump.
 *
 *   weekly-yarn-bump.js [--to VER|--resolve-latest] [--branch main] [--dry-run] [--no-push]
 */
"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const bumpYarn = require("./bump-yarn.js");

const TOPIC = "chore/automated-yarn-bump";
const BOT_NAME = "rhdh-bot service account";
const BOT_EMAIL = "rhdh-bot@redhat.com";

const REPOS = [
  {
    id: "rhdh-plugins",
    host: "github",
    slug: "redhat-developer/rhdh-plugins",
    copyBin: false,
  },
  { id: "rhdh", host: "github", slug: "redhat-developer/rhdh", copyBin: false },
  {
    id: "overlays",
    host: "github",
    slug: "redhat-developer/rhdh-plugin-export-overlays",
    copyBin: false,
  },
  {
    id: "rhdh-cli",
    host: "github",
    slug: "redhat-developer/rhdh-cli",
    copyBin: false,
  },
  { id: "rhidp-rhdh", host: "gitlab", slug: "rhidp/rhdh", copyBin: true },
  {
    id: "rhidp-catalog",
    host: "gitlab",
    slug: "rhidp/rhdh-plugin-catalog",
    copyBin: true,
  },
];

function parseArgs(argv) {
  const a = {
    to: null,
    resolveLatest: true,
    branch: "main",
    dryRun: false,
    push: true,
    locks: true,
    workdir: null,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const x = argv[i];
    if (x === "-h" || x === "--help") {
      console.log(`Usage:
  weekly-yarn-bump.js [--to VER | --resolve-latest] [--branch main]
                      [--dry-run] [--no-push] [--no-refresh-locks] [--workdir DIR]

Resolves latest Yarn 4.x (never 5.x), clones the live-line repos, bumps pins +
lockfiles, opens GitHub PRs / GitLab CEE MRs. Skip if already on --to, denylist,
or an open ${TOPIC}* PR/MR exists.

Env: GITHUB_TOKEN or GH_TOKEN; PRIVATE_TOKEN (GitLab CEE); optional CI_SERVER_HOST.`);
      process.exit(0);
    }
    if (x === "--dry-run") a.dryRun = true;
    else if (x === "--no-push") a.push = false;
    else if (x === "--no-refresh-locks") a.locks = false;
    else if (x === "--resolve-latest") a.resolveLatest = true;
    else if (x === "--to") {
      a.to = argv[++i];
      a.resolveLatest = false;
    } else if (x === "--branch") a.branch = argv[++i];
    else if (x === "--workdir") a.workdir = path.resolve(argv[++i]);
    else {
      console.error(`Unknown: ${x}`);
      process.exit(1);
    }
  }
  return a;
}

function cmpSemver(a, b) {
  const pa = String(a).split(".").map(Number);
  const pb = String(b).split(".").map(Number);
  for (let i = 0; i < 3; i += 1) {
    const d = (pa[i] || 0) - (pb[i] || 0);
    if (d) return d;
  }
  return 0;
}

function pickLatest4(versions) {
  const v4 = versions.map(String).filter((v) => /^4\.\d+\.\d+/.test(v));
  v4.sort(cmpSemver);
  return v4.at(-1) || null;
}

function firstMatchingPrUrl(items, prefix) {
  for (const p of items || []) {
    const head = String(p.headRefName || p.source_branch || "");
    if (!head.startsWith(prefix)) continue;
    return p.url || p.web_url || "";
  }
  return "";
}

function sh(cmd, args, opts = {}) {
  return spawnSync(cmd, args, {
    encoding: "utf8",
    stdio: opts.stdio || ["ignore", "pipe", "pipe"],
    cwd: opts.cwd,
    env: {
      ...process.env,
      GIT_TERMINAL_PROMPT: "0",
      GH_PROMPT: "never",
      ...(opts.env || {}),
    },
  });
}

function resolveLatestYarn4() {
  const r = sh("npm", ["view", "@yarnpkg/cli", "versions", "--json"]);
  if (r.status) {
    throw new Error(`npm view @yarnpkg/cli failed: ${r.stderr || r.stdout}`);
  }
  const versions = JSON.parse(r.stdout);
  const latest = pickLatest4(Array.isArray(versions) ? versions : [versions]);
  if (!latest) throw new Error("no Yarn 4.x versions on npm (@yarnpkg/cli)");
  return latest;
}

function githubToken() {
  return process.env.GITHUB_TOKEN || process.env.GH_TOKEN || "";
}

function githubCloneUrl(slug) {
  const tok = githubToken();
  if (tok) return `https://x-access-token:${tok}@github.com/${slug}.git`;
  return `https://github.com/${slug}.git`;
}

function gitlabHost() {
  return process.env.CI_SERVER_HOST || "gitlab.cee.redhat.com";
}

function gitlabCloneUrl(slug) {
  const tok = process.env.PRIVATE_TOKEN || "";
  const host = gitlabHost();
  const user = process.env.CI_PROJECT_NAME || "oauth2";
  if (tok) return `https://${user}:${tok}@${host}/${slug}.git`;
  return `https://${host}/${slug}.git`;
}

function gitConfigBot(dir) {
  sh("git", ["config", "user.name", BOT_NAME], { cwd: dir });
  sh("git", ["config", "user.email", BOT_EMAIL], { cwd: dir });
}

function cloneRepo(spec, dest, branch) {
  const url =
    spec.host === "github"
      ? githubCloneUrl(spec.slug)
      : gitlabCloneUrl(spec.slug);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  const r = sh("git", [
    "clone",
    "--branch",
    branch,
    "--single-branch",
    "--depth",
    "50",
    url,
    dest,
  ]);
  if (r.status) {
    throw new Error(`clone ${spec.slug} failed: ${r.stderr || r.stdout}`);
  }
  gitConfigBot(dest);
}

function ghJson(args, cwd) {
  const r = sh("gh", args, { cwd });
  if (r.status) return [];
  try {
    return JSON.parse(r.stdout || "[]");
  } catch {
    return [];
  }
}

function gitlabOpenMrs(slug, branch) {
  const tok = process.env.PRIVATE_TOKEN;
  if (!tok) return [];
  const host = gitlabHost();
  const enc = encodeURIComponent(slug);
  const url = `https://${host}/api/v4/projects/${enc}/merge_requests?state=opened&target_branch=${encodeURIComponent(branch)}`;
  const r = sh("curl", ["-fsS", "--header", `PRIVATE-TOKEN: ${tok}`, url]);
  if (r.status) return [];
  try {
    return JSON.parse(r.stdout || "[]");
  } catch {
    return [];
  }
}

function skipReason(spec, dir, branch, to, from) {
  if (!from.length) return `already on ${to} (or only denylist pins)`;
  if (spec.host === "github") {
    const prs = ghJson(
      [
        "pr",
        "list",
        "--base",
        branch,
        "--state",
        "open",
        "--author",
        "rhdh-bot",
        "--json",
        "url,headRefName",
      ],
      dir,
    );
    const url = firstMatchingPrUrl(prs, TOPIC);
    if (url) return `open PR ${url}`;
  } else {
    const mrs = gitlabOpenMrs(spec.slug, branch);
    const url = firstMatchingPrUrl(mrs, TOPIC);
    if (url) return `open MR ${url}`;
  }
  return "";
}

function dirty(dir) {
  const r = sh("git", ["status", "--porcelain"], { cwd: dir });
  return Boolean((r.stdout || "").trim());
}

function commitAndPush(spec, dir, branch, to, { dryRun, push }) {
  if (dryRun) {
    console.log(`dry-run: commit/push ${spec.id}`);
    return { url: "", skipped: "dry-run" };
  }
  if (!dirty(dir)) return { url: "", skipped: "no-diff" };
  sh("git", ["checkout", "-B", TOPIC], { cwd: dir });
  sh("git", ["add", "-A"], { cwd: dir });
  const msg = `chore(deps): bump Yarn to ${to}\n\nOpened by weekly-yarn-bump (rhdh-yarn-bump skill).\n`;
  const c = sh("git", ["commit", "-s", "-m", msg], { cwd: dir });
  if (c.status) return { url: "", skipped: "commit-failed", error: c.stderr };
  if (!push) return { url: "", skipped: "no-push" };
  const p = sh("git", ["push", "-u", "origin", `HEAD:${TOPIC}`], { cwd: dir });
  if (p.status) return { url: "", skipped: "push-failed", error: p.stderr };
  return openPrMr(spec, dir, branch, to);
}

function prBody(to) {
  return `## Summary
- Bump Yarn Berry to \`${to}\` across pins Renovate no longer updates (\`packageManager\`, \`yarnPath\`, extras).
- Use the [rhdh-yarn-bump](https://github.com/redhat-developer/rhdh-skills/blob/main/skills/ci/rhdh-yarn-bump/SKILL.md) skill / weekly-maintenance job.

## Test plan
- [ ] \`yarn --version\` is ${to}
- [ ] lockfiles install with the new binary
`;
}

function openPrMr(spec, dir, branch, to) {
  const title = `chore(deps): bump Yarn to ${to}`;
  if (spec.host === "github") {
    const r = sh(
      "gh",
      [
        "pr",
        "create",
        "--base",
        branch,
        "--head",
        TOPIC,
        "--title",
        title,
        "--body",
        prBody(to),
      ],
      { cwd: dir },
    );
    const url =
      (r.stdout || "")
        .trim()
        .split("\n")
        .filter((l) => l.includes("github.com"))
        .at(-1) || "";
    if (url)
      sh("gh", ["pr", "edit", url, "--add-label", "ok-to-test"], { cwd: dir });
    if (!url) return { url: "", skipped: "pr-create-failed", error: r.stderr };
    return { url };
  }
  return openGitlabMr(spec.slug, branch, title, to);
}

function openGitlabMr(slug, target, title, to) {
  const tok = process.env.PRIVATE_TOKEN;
  if (!tok) return { url: "", skipped: "no-PRIVATE_TOKEN" };
  const host = gitlabHost();
  const enc = encodeURIComponent(slug);
  const payload = JSON.stringify({
    source_branch: TOPIC,
    target_branch: target,
    title,
    description: prBody(to),
    remove_source_branch: true,
  });
  const r = sh("curl", [
    "-fsS",
    "--request",
    "POST",
    "--header",
    `PRIVATE-TOKEN: ${tok}`,
    "--header",
    "Content-Type: application/json",
    "--data",
    payload,
    `https://${host}/api/v4/projects/${enc}/merge_requests`,
  ]);
  try {
    const j = JSON.parse(r.stdout || "{}");
    return {
      url: j.web_url || "",
      skipped: j.web_url ? "" : "mr-create-failed",
      error: r.stderr,
    };
  } catch {
    return {
      url: "",
      skipped: "mr-create-failed",
      error: r.stderr || r.stdout,
    };
  }
}

function logResult(row) {
  const bits = [
    `repo: ${row.id}`,
    `host: ${row.host}`,
    `from: ${row.from || "-"}`,
    `to: ${row.to}`,
  ];
  if (row.skipped) bits.push(`skipped: ${row.skipped}`);
  if (row.url) bits.push(`url: ${row.url}`);
  if (row.error) bits.push(`error: ${String(row.error).trim().split("\n")[0]}`);
  console.log(bits.join("\n"));
  console.log("---");
}

function processRepo(spec, dir, args, to, ghBinRoot) {
  const row = {
    id: spec.id,
    host: spec.host,
    to,
    from: "",
    url: "",
    skipped: "",
    error: "",
  };
  try {
    const from = bumpYarn.collectFromVersions(dir, to);
    row.from = from.join(",");
    const reason = skipReason(spec, dir, args.branch, to, from);
    if (reason) {
      row.skipped = reason;
      return row;
    }
    if (spec.copyBin) {
      if (!ghBinRoot)
        throw new Error("no GitHub yarn binary to copy; bump a GH repo first");
      bumpYarn.copyYarnBin(ghBinRoot, dir, to, args.dryRun);
    }
    bumpYarn.bump(dir, {
      from,
      to,
      dryRun: args.dryRun,
      locks: args.locks,
    });
    const opened = commitAndPush(spec, dir, args.branch, to, args);
    Object.assign(row, opened);
  } catch (err) {
    row.error = err.message || String(err);
  }
  return row;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const to = args.to || (args.resolveLatest ? resolveLatestYarn4() : null);
  if (!to) {
    console.error("--to VERSION or --resolve-latest required");
    process.exit(1);
  }
  console.log(
    `to=${to} branch=${args.branch} dry-run=${args.dryRun} push=${args.push} locks=${args.locks}`,
  );

  const workdir =
    args.workdir || fs.mkdtempSync(path.join(os.tmpdir(), "weekly-yarn-"));
  fs.mkdirSync(workdir, { recursive: true });

  const results = [];
  let ghBinRoot = null;
  let failed = 0;

  const ordered = [
    ...REPOS.filter((r) => r.host === "github"),
    ...REPOS.filter((r) => r.host === "gitlab"),
  ];
  for (const spec of ordered) {
    const dir = path.join(workdir, spec.id);
    try {
      cloneRepo(spec, dir, args.branch);
    } catch (err) {
      const row = {
        id: spec.id,
        host: spec.host,
        to,
        from: "",
        skipped: "clone-failed",
        error: err.message,
      };
      results.push(row);
      failed += 1;
      logResult(row);
      continue;
    }
    const row = processRepo(spec, dir, args, to, ghBinRoot);
    if (!spec.copyBin && !row.skipped) {
      const bin = path.join(dir, ".yarn", "releases", `yarn-${to}.cjs`);
      if (fs.existsSync(bin)) ghBinRoot = dir;
    }
    if (row.error || (row.skipped && /failed/.test(row.skipped))) failed += 1;
    results.push(row);
    logResult(row);
  }

  console.log(`done: ${results.length} repos, failures=${failed}`);
  if (failed) process.exit(1);
}

module.exports = {
  REPOS,
  TOPIC,
  pickLatest4,
  firstMatchingPrUrl,
  parseArgs,
};

if (require.main === module) main();
