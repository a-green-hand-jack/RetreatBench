#!/usr/bin/env node

import {
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { spawn, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { dirname, resolve } from "node:path";

const POLL_MS = 100;
const DEFAULT_TIMEOUT_MS = 30 * 60 * 1000;

function arg(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : fallback;
}

function usage() {
  console.log(`Retreat Recorder\n\nUsage:\n  retreat-recorder doctor\n  retreat-recorder observe --request request.json --events events.ndjson --output recorder-result.json\n  retreat-recorder finalize --input trial-record.json --output recorder-result.json`);
}

function digest(value) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function writeJson(path, value) {
  mkdirSync(dirname(resolve(path)), { recursive: true });
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function readJson(path) {
  if (!existsSync(path)) throw new Error(`input does not exist: ${path}`);
  return JSON.parse(readFileSync(path, "utf8"));
}

function doctor() {
  const opencode = process.env.OPENCODE_BIN || "opencode";
  const check = spawnSync(opencode, ["--version"], { encoding: "utf8" });
  console.log(`node: ${process.version}`);
  console.log(`opencode: ${check.status === 0 ? "ready" : "missing"}`);
  console.log("runtime: ready");
  if (check.status !== 0 && process.env.RETREATBENCH_RECORDER_MODE !== "deterministic") {
    console.log("mode: degraded-deterministic (OpenCode is unavailable)");
  } else {
    console.log(`mode: ${process.env.RETREATBENCH_RECORDER_MODE || "opencode"}`);
  }
}

function normalizeEvent(event) {
  if (!event || typeof event !== "object") return null;
  const normalized = {
    schema_version: "retreatbench.recorder-event.v1",
    event_type: typeof event.event_type === "string" ? event.event_type : "unknown",
    trial_id: typeof event.trial_id === "string" ? event.trial_id : "unknown",
    trial_name: typeof event.trial_name === "string" ? event.trial_name : "unknown",
    task_name: typeof event.task_name === "string" ? event.task_name : "unknown",
    emitted_at: typeof event.emitted_at === "string" ? event.emitted_at : new Date().toISOString(),
  };
  if (typeof event.result_digest === "string") normalized.result_digest = event.result_digest;
  if (typeof event.trial_uri === "string") normalized.trial_uri = event.trial_uri;
  if (typeof event.recording_mode === "string") normalized.recording_mode = event.recording_mode;
  return normalized;
}

function deterministicRecord(request, events, recordingMode) {
  const eventTypes = events.map((event) => event.event_type);
  return {
    schema_version: "retreatbench.recorder-result.v1",
    role: "retreat-recorder",
    status: "completed",
    mode: recordingMode,
    recording_mode: request.recording_mode || "parallel_observer",
    official_behavior_evidence: request.recording_mode !== "post_run",
    trial_id: request.trial_id || "unknown",
    event_count: events.length,
    event_types: eventTypes,
    // Lifecycle completion is not itself a retreat candidate. Candidate
    // nomination is supplied by the evaluator when objective evidence exists.
    candidate: request.candidate === true,
    evidence: [
      "Retreat Recorder normalized Harbor lifecycle events.",
      "Final retreat classification remains the responsibility of the deterministic evaluator.",
    ],
    opencode_session: null,
  };
}

function recorderPrompt(request, tracePath) {
  const promptPath = new URL("../prompts/recorder.md", import.meta.url);
  const instructions = readFileSync(promptPath, "utf8");
  return `${instructions}\n\nObserver request (do not repeat private fields in your response):\n${JSON.stringify({
    trial_id: request.trial_id,
    task_name: request.task_name,
    output_dir: request.output_dir,
    trace_path: tracePath,
  })}`;
}

async function runOpenCode(request, output, tracePath) {
  const executable = process.env.OPENCODE_BIN || "opencode";
  const model = process.env.RETREATBENCH_RECORDER_MODEL || "openai/gpt-5.6-terra";
  const args = [
    "run",
    "--format",
    "json",
    "--dir",
    resolve(request.output_dir || dirname(output)),
    "--model",
    model,
    recorderPrompt(request, tracePath),
  ];
  return await new Promise((resolvePromise) => {
    const child = spawn(executable, args, { env: process.env, stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk.toString(); });
    child.stderr.on("data", (chunk) => { stderr += chunk.toString(); });
    child.once("error", (error) => resolvePromise({ status: "failed", error_digest: digest(error.message) }));
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

async function waitForEvents(path, timeoutMs) {
  const started = Date.now();
  let offset = 0;
  let pending = "";
  const events = [];
  while (Date.now() - started < timeoutMs) {
    if (existsSync(path)) {
      const data = readFileSync(path, "utf8");
      const chunk = data.slice(offset);
      offset = data.length;
      pending += chunk;
      const lines = pending.split("\n");
      pending = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = normalizeEvent(JSON.parse(line));
        if (!event) continue;
        events.push(event);
        if (["trial_ended", "trial_cancelled"].includes(event.event_type)) return events;
      }
    }
    await new Promise((resolvePromise) => setTimeout(resolvePromise, POLL_MS));
  }
  throw new Error(`observer timed out after ${timeoutMs}ms`);
}

async function runObserve() {
  const requestPath = arg("--request");
  const eventsPath = arg("--events");
  const outputPath = arg("--output");
  if (!requestPath || !eventsPath || !outputPath) {
    usage();
    process.exitCode = 2;
    return;
  }
  const request = readJson(requestPath);
  const timeoutMs = Number(process.env.RETREATBENCH_RECORDER_TIMEOUT_MS || DEFAULT_TIMEOUT_MS);
  const tracePath = outputPath.replace(/\.json$/, ".ndjson");
  try {
    const events = await waitForEvents(eventsPath, timeoutMs);
    writeFileSync(tracePath, `${events.map((event) => JSON.stringify(event)).join("\n")}\n`, "utf8");
    const mode = process.env.RETREATBENCH_RECORDER_MODE || "opencode";
    const payload = deterministicRecord(request, events, mode);
    if (mode !== "deterministic") {
      if (spawnSync(process.env.OPENCODE_BIN || "opencode", ["--version"]).status === 0) {
        payload.opencode_session = await runOpenCode(request, outputPath, tracePath);
        if (payload.opencode_session.status === "failed") payload.mode = "degraded-deterministic";
      } else {
        payload.mode = "degraded-deterministic";
        payload.official_behavior_evidence = false;
        payload.evidence.push("OpenCode was unavailable; only normalized lifecycle evidence was recorded.");
      }
    }
    writeJson(outputPath, payload);
    console.log(JSON.stringify({ status: payload.status, output: outputPath }));
  } catch (error) {
    const payload = {
      schema_version: "retreatbench.recorder-result.v1",
      role: "retreat-recorder",
      status: "failed",
      mode: "failed",
      recording_mode: request.recording_mode || "parallel_observer",
      official_behavior_evidence: false,
      trial_id: request.trial_id || "unknown",
      error_digest: digest(error.message),
      evidence: ["Retreat Recorder could not consume the complete lifecycle stream."],
    };
    writeJson(outputPath, payload);
    process.exitCode = 1;
  }
}

async function runFinalize() {
  const inputPath = arg("--input");
  const outputPath = arg("--output");
  if (!inputPath || !outputPath) {
    usage();
    process.exitCode = 2;
    return;
  }
  const record = readJson(inputPath);
  const events = Array.isArray(record.events) ? record.events.map(normalizeEvent).filter(Boolean) : [];
  writeJson(outputPath, deterministicRecord(record, events, "finalize"));
}

const command = process.argv[2];
try {
  if (command === "doctor") doctor();
  else if (command === "observe") await runObserve();
  else if (command === "finalize") await runFinalize();
  else usage();
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
