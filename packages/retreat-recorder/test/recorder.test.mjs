import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { execFileSync } from "node:child_process";

test("observer emits structured result after the lifecycle closes", () => {
  const dir = mkdtempSync(join(tmpdir(), "retreat-recorder-"));
  const input = join(dir, "request.json");
  const events = join(dir, "events.ndjson");
  const output = join(dir, "result.json");
  writeFileSync(input, JSON.stringify({ trial_id: "t1", recording_mode: "parallel_observer" }));
  writeFileSync(events, [
    JSON.stringify({ event_type: "trial_started", trial_id: "t1" }),
    JSON.stringify({ event_type: "agent_ended", trial_id: "t1" }),
    JSON.stringify({ event_type: "trial_ended", trial_id: "t1" }),
  ].join("\n") + "\n");
  execFileSync(process.execPath, ["src/cli.mjs", "observe", "--request", input, "--events", events, "--output", output], {
    cwd: new URL("..", import.meta.url),
    env: { ...process.env, RETREATBENCH_RECORDER_MODE: "deterministic" },
  });
  const result = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(result.schema_version, "retreatbench.recorder-result.v1");
  assert.equal(result.role, "retreat-recorder");
  assert.equal(result.event_count, 3);
  assert.deepEqual(result.event_types, ["trial_started", "agent_ended", "trial_ended"]);
  assert.equal(result.candidate, false);
  assert.equal(result.official_behavior_evidence, false);
});

test("default observer records a degraded status when OpenCode is unavailable", () => {
  const dir = mkdtempSync(join(tmpdir(), "retreat-recorder-degraded-"));
  const input = join(dir, "request.json");
  const events = join(dir, "events.ndjson");
  const output = join(dir, "result.json");
  writeFileSync(input, JSON.stringify({ trial_id: "t2", recording_mode: "parallel_observer" }));
  writeFileSync(events, `${JSON.stringify({ event_type: "trial_ended", trial_id: "t2" })}\n`);
  execFileSync(process.execPath, ["src/cli.mjs", "observe", "--request", input, "--events", events, "--output", output], {
    cwd: new URL("..", import.meta.url),
    env: { ...process.env, OPENCODE_BIN: "/does/not/exist", RETREATBENCH_RECORDER_TIMEOUT_MS: "1000" },
  });
  const result = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(result.mode, "degraded-deterministic");
  assert.equal(result.official_behavior_evidence, false);
});

test("finalize produces a deterministic recorder result", () => {
  const dir = mkdtempSync(join(tmpdir(), "retreat-recorder-finalize-"));
  const input = join(dir, "trial-record.json");
  const output = join(dir, "result.json");
  writeFileSync(input, JSON.stringify({ trial_id: "t3", recording_mode: "post_run", events: [] }));
  execFileSync(process.execPath, ["src/cli.mjs", "finalize", "--input", input, "--output", output], {
    cwd: new URL("..", import.meta.url),
  });
  const result = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(result.status, "completed");
  assert.equal(result.official_behavior_evidence, false);
});
