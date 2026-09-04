import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { execFileSync } from "node:child_process";

test("sidecar emits structured result", () => {
  const dir = mkdtempSync(join(tmpdir(), "retreat-auditor-"));
  const input = join(dir, "request.json");
  const output = join(dir, "result.json");
  writeFileSync(input, JSON.stringify({ trial_id: "t1", performer_result: { trajectory: [] } }));
  execFileSync(process.execPath, ["src/cli.mjs", "sidecar", "--input", input, "--output", output], {
    cwd: new URL("..", import.meta.url),
  });
  const result = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(result.schema_version, "retreatbench.auditor-result.v1");
  assert.equal(result.role, "retreat-auditor");
});
