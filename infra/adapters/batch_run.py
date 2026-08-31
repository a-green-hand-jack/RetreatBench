#!/usr/bin/env python3
"""Batch-convert, dually-verify, and selectively publish upstream tasks.

Per (benchmark, task_id):
  1. Convert via the Stevedore opencode agent (same agent/prompt as
     infra/adapters/<slug>/convert.sh, invoked directly here for
     concurrency control and structured result capture).
  2. Mechanical verification (infra/adapters/verify_task.py, as a
     subprocess): task.toml schema, real environment build, reward-file
     wiring in tests/test.sh, and (ResearchClawBench only) the private
     ground-truth leak check.
  3. A real `harbor run` smoke test: n-attempts 1, a short
     agent-timeout-multiplier, subject agent = opencode/openai via Apex
     first. PASS is defined as: the trial produced a valid, parseable
     reward file (harbor/verifier/reward.txt or reward.json) -- this
     validates that the CONVERSION's build+agent+verify machinery works
     end to end, not that the subject agent actually solved the task (this
     is the same "candidate detectors don't establish capability" stance
     the rest of the project takes -- see docs/benchmark-hub.md). If no
     reward file was produced and the recorded exception looks
     credential/balance-related, retry once with OpenAI OAuth (the codex
     agent + CODEX_AUTH_JSON_PATH, matching
     infra/benchmarks/terminal-bench-2/gpt2-codegolf.yaml's
     `provider: openai-oauth` pattern) if that credential file exists and
     is non-empty; otherwise log BLOCKED_ON_CREDENTIALS and move on. Never
     retries more than once per credential path, never spins.
  4. Only a task that passes BOTH steps 2 and 3 is published immediately
     (hf upload) to Jack-Jieke-Wu/Avoidance-Behavior-Exam/<benchmark>/<task_id>/
     -- publishing per task as it passes, not batched at the very end, so
     an interrupted run never loses already-validated progress.

Every outcome is appended as one JSON line to --log-file: {benchmark,
task_id, timestamp, mechanical: {status, detail}, harbor_run: {status,
detail, credential_used, reward}, published}. status is one of PASS,
MECHANICAL_FAIL, HARBOR_RUN_FAIL, BLOCKED_ON_CREDENTIALS, CONVERT_FAILED.

Usage:
    python3 infra/adapters/batch_run.py \
        --benchmark terminal-bench-1x \
        --upstream-root upstreams/terminal-bench/original-tasks \
        --output-root upstreams/converted/terminal-bench-1x \
        --agent-name stevedore-tb1x \
        --target-hub-path terminal-bench-1x \
        --task-ids-file /tmp/tb1x_task_ids.txt \
        --concurrency 5 \
        --log-file upstreams/converted/terminal-bench-1x/batch_log.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import re
import time
from pathlib import Path

HF_TARGET_REPO = "Jack-Jieke-Wu/Avoidance-Behavior-Exam"
CONVERT_MODEL = "openai/gpt-5.6-sol"
HARBOR_MODEL = "openai/gpt-5.6-sol"
CODEX_MODEL = "openai/gpt-5.6-sol"
AGENT_TIMEOUT_MULTIPLIER = "0.5"
VERIFIER_TIMEOUT_MULTIPLIER = "3.0"  # some verifiers (e.g. build-initramfs-qemu) need more than the upstream's 180s default
CONVERT_TIMEOUT_SEC = 900  # bumped: some tasks have large auxiliary data files
HARBOR_TIMEOUT_SEC = 2100  # bumped for a heavy-task retry pass (kernel/QEMU builds etc.)
CODEX_AUTH_JSON_PATH = str(Path.home() / ".codex" / "auth.json")
CREDENTIAL_ERROR_PATTERNS = re.compile(
    r"insufficient account balance|insufficient_quota|invalid_api_key|"
    r"unauthorized|401|no available channel|model_not_found",
    re.IGNORECASE,
)


def log_line(log_file: Path, record: dict) -> None:
    record = {**record, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    print(f"[{record['benchmark']}/{record['task_id']}] {record['status']}: {record.get('detail', '')}")


async def run_cmd(cmd: list[str], *, cwd: Path | None = None, timeout: int, env: dict | None = None) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, f"timed out after {timeout}s"
    return proc.returncode, out.decode(errors="replace")


async def convert_task(
    *, task_id: str, upstream_dir: Path, out_dir: Path, agent_name: str, prompt_template: str
) -> tuple[bool, str]:
    prompt = prompt_template.replace("{upstream_task_dir}", str(upstream_dir)).replace(
        "{output_dir}", str(out_dir)
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    code, output = await run_cmd(
        ["opencode", "run", "--agent", agent_name, "-m", CONVERT_MODEL, "--format", "json", prompt],
        timeout=CONVERT_TIMEOUT_SEC,
    )
    if code != 0:
        return False, f"opencode exit {code}: {output[-1500:]}"
    return True, output[-500:]


async def mechanical_verify(
    *, out_dir: Path, private_source: Path | None, repo_root: Path
) -> tuple[bool, str]:
    cmd = ["python3", str(repo_root / "infra" / "adapters" / "verify_task.py"), str(out_dir)]
    if private_source is not None:
        cmd += ["--private-source", str(private_source)]
    code, output = await run_cmd(cmd, timeout=1800)  # bumped for a heavy-task retry pass
    return code == 0, output[-1500:]


def find_reward_file(job_dir: Path, task_id: str) -> Path | None:
    # Harbor truncates long task ids when naming the trial directory (e.g.
    # "decommissioning-service-with-sensitive-data__yaiLMXt" becomes
    # "decommissioning-service-with-sen__yaiLMXt") -- glob on "*__*" instead
    # of assuming the full task_id is the directory prefix verbatim. Each
    # job_dir here holds exactly one trial (n-attempts=1, one task per job),
    # so taking the sole matching trial directory is unambiguous. (Found
    # empirically: a real trial with reward=1.0 was being logged as FAIL
    # because this glob never matched the truncated directory name.)
    for pattern in ("reward.txt", "reward.json"):
        matches = glob.glob(str(job_dir / "*__*" / "verifier" / pattern))
        if matches:
            return Path(matches[0])
    return None


def find_exception_file(job_dir: Path, task_id: str) -> Path | None:
    matches = glob.glob(str(job_dir / "*__*" / "exception.txt"))
    return Path(matches[0]) if matches else None


async def harbor_run_once(
    *, task_dir: Path, job_name: str, repo_root: Path, credential: str, env_file: Path | None
) -> tuple[int, str]:
    cmd = [
        "harbor",
        "run",
        "--path",
        str(task_dir),
        "--n-attempts",
        "1",
        "--n-concurrent",
        "1",
        "--agent-timeout-multiplier",
        AGENT_TIMEOUT_MULTIPLIER,
        "--verifier-timeout-multiplier",
        VERIFIER_TIMEOUT_MULTIPLIER,
        "--job-name",
        job_name,
        "--yes",
    ]
    if credential == "apex":
        cmd += ["--agent", "opencode", "--model", HARBOR_MODEL]
        if env_file is not None:
            cmd += ["--env-file", str(env_file)]
    elif credential == "oauth":
        cmd += ["--agent", "codex", "--model", CODEX_MODEL, "--ae", f"CODEX_AUTH_JSON_PATH={CODEX_AUTH_JSON_PATH}"]
    else:
        raise ValueError(credential)
    return await run_cmd(cmd, cwd=repo_root, timeout=HARBOR_TIMEOUT_SEC)


async def harbor_run_with_fallback(
    *, task_id: str, task_dir: Path, repo_root: Path, env_file: Path | None
) -> tuple[str, str, str | None, str | None]:
    """Returns (status, detail, credential_used, reward)."""

    oauth_available = Path(CODEX_AUTH_JSON_PATH).is_file() and Path(CODEX_AUTH_JSON_PATH).stat().st_size > 0

    job_name = f"batch-{task_id}-apex-{int(time.time())}"
    job_dir = repo_root / "jobs" / job_name
    code, output = await harbor_run_once(
        task_dir=task_dir, job_name=job_name, repo_root=repo_root, credential="apex", env_file=env_file
    )
    reward_file = find_reward_file(job_dir, task_id)
    if reward_file is not None:
        try:
            reward = reward_file.read_text().strip()
            float(reward)
            return "PASS", output[-800:], "apex", reward
        except ValueError:
            pass

    exc_file = find_exception_file(job_dir, task_id)
    exc_text = exc_file.read_text(errors="replace") if exc_file else output
    credential_issue = bool(CREDENTIAL_ERROR_PATTERNS.search(exc_text))

    if not credential_issue:
        return "HARBOR_RUN_FAIL", exc_text[-1500:], "apex", None

    if not oauth_available:
        return (
            "BLOCKED_ON_CREDENTIALS",
            f"Apex failed with a credential/balance-looking error and no OAuth fallback "
            f"available at {CODEX_AUTH_JSON_PATH}: {exc_text[-800:]}",
            "apex",
            None,
        )

    job_name_oauth = f"batch-{task_id}-oauth-{int(time.time())}"
    job_dir_oauth = repo_root / "jobs" / job_name_oauth
    code2, output2 = await harbor_run_once(
        task_dir=task_dir, job_name=job_name_oauth, repo_root=repo_root, credential="oauth", env_file=None
    )
    reward_file2 = find_reward_file(job_dir_oauth, task_id)
    if reward_file2 is not None:
        try:
            reward2 = reward_file2.read_text().strip()
            float(reward2)
            return "PASS", output2[-800:], "oauth-fallback", reward2
        except ValueError:
            pass

    exc_file2 = find_exception_file(job_dir_oauth, task_id)
    exc_text2 = exc_file2.read_text(errors="replace") if exc_file2 else output2
    if CREDENTIAL_ERROR_PATTERNS.search(exc_text2):
        return "BLOCKED_ON_CREDENTIALS", f"Both apex and oauth failed on credentials: {exc_text2[-800:]}", "oauth-fallback", None
    return "HARBOR_RUN_FAIL", exc_text2[-1500:], "oauth-fallback", None


async def publish_task(*, out_dir: Path, target_hub_path: str, task_id: str) -> tuple[bool, str]:
    code, output = await run_cmd(
        [
            "hf",
            "upload",
            HF_TARGET_REPO,
            str(out_dir),
            f"{target_hub_path}/{task_id}",
            "--repo-type",
            "dataset",
            "--commit-message",
            f"Publish {target_hub_path}/{task_id} (passed mechanical + real harbor run)",
        ],
        timeout=600,
    )
    return code == 0, output[-800:]


async def process_task(
    *,
    task_id: str,
    benchmark: str,
    upstream_root: Path,
    output_root: Path,
    agent_name: str,
    prompt_template: str,
    target_hub_path: str,
    private_source_subpath: str | None,
    repo_root: Path,
    env_file: Path | None,
    log_file: Path,
    semaphore: asyncio.Semaphore,
    skip_publish: bool,
) -> None:
    async with semaphore:
        upstream_dir = upstream_root / task_id
        out_dir = output_root / task_id
        record = {"benchmark": benchmark, "task_id": task_id}

        ok, detail = await convert_task(
            task_id=task_id, upstream_dir=upstream_dir, out_dir=out_dir, agent_name=agent_name, prompt_template=prompt_template
        )
        if not ok:
            log_line(log_file, {**record, "status": "CONVERT_FAILED", "detail": detail})
            return

        private_source = (upstream_dir / private_source_subpath) if private_source_subpath else None
        ok, detail = await mechanical_verify(out_dir=out_dir, private_source=private_source, repo_root=repo_root)
        if not ok:
            log_line(log_file, {**record, "status": "MECHANICAL_FAIL", "detail": detail})
            return

        status, detail, credential_used, reward = await harbor_run_with_fallback(
            task_id=task_id, task_dir=out_dir, repo_root=repo_root, env_file=env_file
        )
        if status != "PASS":
            log_line(log_file, {**record, "status": status, "detail": detail, "credential_used": credential_used})
            return

        published = False
        publish_detail = "skipped (--skip-publish)"
        if not skip_publish:
            published, publish_detail = await publish_task(out_dir=out_dir, target_hub_path=target_hub_path, task_id=task_id)

        log_line(
            log_file,
            {
                **record,
                "status": "PASS",
                "detail": detail,
                "credential_used": credential_used,
                "reward": reward,
                "published": published,
                "publish_detail": publish_detail,
            },
        )


async def main_async(args: argparse.Namespace) -> None:
    repo_root = Path(args.repo_root).resolve()
    upstream_root = Path(args.upstream_root).resolve()
    output_root = Path(args.output_root).resolve()
    log_file = Path(args.log_file).resolve()
    log_file.parent.mkdir(parents=True, exist_ok=True)

    prompt_template = Path(args.prompt_template).read_text(encoding="utf-8")
    task_ids = [line.strip() for line in Path(args.task_ids_file).read_text().splitlines() if line.strip()]

    semaphore = asyncio.Semaphore(args.concurrency)
    env_file = Path(args.env_file).resolve() if args.env_file else None

    tasks = [
        process_task(
            task_id=task_id,
            benchmark=args.benchmark,
            upstream_root=upstream_root,
            output_root=output_root,
            agent_name=args.agent_name,
            prompt_template=prompt_template,
            target_hub_path=args.target_hub_path,
            private_source_subpath=args.private_source_subpath,
            repo_root=repo_root,
            env_file=env_file,
            log_file=log_file,
            semaphore=semaphore,
            skip_publish=args.skip_publish,
        )
        for task_id in task_ids
    ]
    await asyncio.gather(*tasks)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--upstream-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--agent-name", required=True, help="opencode --agent name, e.g. stevedore-tb1x")
    parser.add_argument("--prompt-template", required=True, help="path to prompt.template.txt")
    parser.add_argument("--target-hub-path", required=True, help="e.g. terminal-bench-1x")
    parser.add_argument("--private-source-subpath", default=None, help="e.g. target_study (ResearchClawBench only)")
    parser.add_argument("--task-ids-file", required=True)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--log-file", required=True)
    parser.add_argument("--env-file", default=None, help="Apex OPENAI_* credentials for the harbor run's subject agent")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--skip-publish", action="store_true", help="dry run: do not hf upload passing tasks")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
