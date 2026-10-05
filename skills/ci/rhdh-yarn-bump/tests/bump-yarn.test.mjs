import assert from "node:assert/strict";
import { createRequire } from "node:module";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const scriptsDir = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "scripts",
);
const bumpYarn = require(path.join(scriptsDir, "bump-yarn.js"));

describe("rewriteExtras", () => {
  it("rewrites yarn binary pins and yarn set version", () => {
    const src =
      "ENV YARN=/.yarn/releases/yarn-4.17.1.cjs\nyarn set version 4.17.1\n";
    const out = bumpYarn.rewriteExtras(src, ["4.17.1"], "4.18.1");
    assert.equal(
      out,
      "ENV YARN=/.yarn/releases/yarn-4.18.1.cjs\nyarn set version 4.18.1\n",
    );
  });
});

describe("collectFromVersions", () => {
  it("collects packageManager pins except denylist and --to", () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "yarn-from-"));
    fs.writeFileSync(
      path.join(root, "package.json"),
      JSON.stringify({ packageManager: "yarn@4.17.1" }),
    );
    fs.mkdirSync(path.join(root, "legacy"), { recursive: true });
    fs.writeFileSync(
      path.join(root, "legacy", "package.json"),
      JSON.stringify({ packageManager: "yarn@4.8.1" }),
    );
    fs.mkdirSync(path.join(root, ".yarn", "releases"), { recursive: true });
    fs.writeFileSync(
      path.join(root, ".yarn", "releases", "yarn-4.17.1.cjs"),
      "//",
    );
    assert.deepEqual(bumpYarn.collectFromVersions(root, "4.18.1"), ["4.17.1"]);
  });

  it("returns empty when already on --to", () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "yarn-to-"));
    fs.writeFileSync(
      path.join(root, "package.json"),
      JSON.stringify({ packageManager: "yarn@4.18.1" }),
    );
    assert.deepEqual(bumpYarn.collectFromVersions(root, "4.18.1"), []);
  });
});

describe("copyYarnBin", () => {
  it("copies yarn-<to>.cjs and removes older binaries", () => {
    const src = fs.mkdtempSync(path.join(os.tmpdir(), "yarn-src-"));
    const dest = fs.mkdtempSync(path.join(os.tmpdir(), "yarn-dst-"));
    fs.mkdirSync(path.join(src, ".yarn", "releases"), { recursive: true });
    fs.mkdirSync(path.join(dest, ".yarn", "releases"), { recursive: true });
    fs.writeFileSync(
      path.join(src, ".yarn", "releases", "yarn-4.18.1.cjs"),
      "new",
    );
    fs.writeFileSync(
      path.join(dest, ".yarn", "releases", "yarn-4.17.1.cjs"),
      "old",
    );
    bumpYarn.copyYarnBin(src, dest, "4.18.1", false);
    assert.equal(
      fs.readFileSync(
        path.join(dest, ".yarn", "releases", "yarn-4.18.1.cjs"),
        "utf8",
      ),
      "new",
    );
    assert.equal(
      fs.existsSync(path.join(dest, ".yarn", "releases", "yarn-4.17.1.cjs")),
      false,
    );
  });
});
