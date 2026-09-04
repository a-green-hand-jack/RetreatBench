#!/usr/bin/env node

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { dirname, resolve } from "node:path";

function arg(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : fallback;
}

function usage() {
  console.log(`Retreat Auditor sidecar\n\nUsage:\n  retreat-auditor doctor\n  retreat-auditor sidecar --input request.json --output result.json`);
}

function doctor() {
  console.log(`node: ${process.version}`);
  console.log(`opencode: ${process.env.OPENCODE_BIN || "opencode (resolved at runtime)"}`);
  console.log("runtime: ready");
}

function deterministicAudit(request) {
  const result = request?.performer_result ?? {};
  return {
    schema_version: "retreatbench.auditor-result.v1",
    role: "retreat-auditor",
    status: "ready",
    mode: "structured-evidence",
    trial_id: request?.trial_id ?? "unknown",
    candidate: Boolean(result?.agent_result || result?.trajectory),
    evidence: [
      "Retreat Auditor received the normalized performer trial result.",
      "Final retreat classification remains the responsibility of the deterministic evaluator."
    ],
    opencode_session: null
  };
}

function opencodePrompt(request) {
  const promptPath = new URL("../prompts/auditor.md", import.meta.url);
  const instructions = readFileSync(promptPath, "utf8");
  return `${instructions}\n\nTrial request (do not repeat private fields in your response):\n${JSON.stringify({
    trial_id: request?.trial_id,
    task_name: request?.task_name,
    output_dir: request?.output_dir,
  })}`;
}

async function runOpenCode(request, output) {
  const executable = process.env.OPENCODE_BIN || "opencode";
  const model = process.env.RETREATBENCH_AUDITOR_MODEL || "openai/gpt-5.6-terra";
  const args = [
    "run",
    "--format",
    "json",
    "--dir",
    resolve(request?.output_dir || dirname(output)),
    "--model",
    model,
    opencodePrompt(request),
  ];
  return await new Promise((resolvePromise) => {
    const child = spawn(executable, args, { env: process.env, stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk.toString(); });
    child.stderr.on("data", (chunk) => { stderr += chunk.toString(); });
    child.once("error", (error) => resolvePromise({ status: "failed", error: error.message }));
    child.once("exit", (code) => {
      if (code !== 0) {
        resolvePromise({ status: "failed", returncode: code, stderr_digest: digest(stderr) });
        return;
      }
      resolvePromise({
        status: "completed",
        model,
        response_digest: digest(stdout),
        response_events: stdout.split("\n").filter(Boolean).length,
      });
    });
  });
}

function digest(value) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

async function runSidecar() {
  const input = arg("--input");
  const output = arg("--output");
  if (!input || !output) {
    usage();
    process.exitCode = 2;
    return;
  }
  if (!existsSync(input)) throw new Error(`input does not exist: ${input}`);
  const request = JSON.parse(readFileSync(input, "utf8"));
  const payload = deterministicAudit(request);
  if (process.env.RETREATBENCH_USE_OPENCODE === "1") {
    payload.mode = "opencode-structured-evidence";
    payload.opencode_session = await runOpenCode(request, output);
  }
  writeFileSync(output, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  console.log(JSON.stringify({ status: payload.status, output }));
}

const command = process.argv[2];
try {
  if (command === "doctor") doctor();
  else if (command === "sidecar") await runSidecar();
  else usage();
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
