from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from retreatbench import detect as detect_module
from retreatbench.cli import app
from retreatbench.detect import (
    DetectError,
    assemble_decision_context,
    build_prompt,
    candidates_agree,
    extract_json_object,
    load_env_file,
    parse_claude_print_json,
    parse_opencode_json_stream,
    run_diagnose_team,
    run_judge,
)
from retreatbench.models import DecisionContext

runner = CliRunner()


def _opencode_stdout(payload: dict) -> str:
    text = json.dumps(payload)
    return json.dumps({"type": "text", "part": {"type": "text", "text": text}}) + "\n"


def _claude_print_stdout(payload: dict) -> str:
    return json.dumps({"result": json.dumps(payload), "is_error": False})


class _FakeCompletedProcess:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def test_load_env_file_parses_key_value_lines(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "# a comment",
                "",
                "OPENAI_API_KEY=sk-example",
                "OPENAI_BASE_URL=https://api.example.com/v1",
                "  ANTHROPIC_API_KEY = with-spaces  ",
            ]
        ),
        encoding="utf-8",
    )
    result = load_env_file(env_path)
    assert result == {
        "OPENAI_API_KEY": "sk-example",
        "OPENAI_BASE_URL": "https://api.example.com/v1",
        "ANTHROPIC_API_KEY": "with-spaces",
    }


def test_load_env_file_missing_file(tmp_path: Path) -> None:
    with pytest.raises(DetectError, match="does not exist"):
        load_env_file(tmp_path / "missing.env")


def test_load_env_file_rejects_malformed_line(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("NOT_A_KEY_VALUE_LINE", encoding="utf-8")
    with pytest.raises(DetectError, match="expected KEY=VALUE"):
        load_env_file(env_path)


def test_build_prompt_inlines_goal_contract_and_evidence(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "instruction.md").write_text("do the specific-marker-xyz task", encoding="utf-8")
    contract_path = tmp_path / "goal_contract.json"
    contract_path.write_text(json.dumps({"task_name": "example-task"}), encoding="utf-8")

    prompt = build_prompt(evidence, contract_path)

    assert "example-task" in prompt
    assert "specific-marker-xyz" in prompt
    assert "PRIVATE GOAL CONTRACT" in prompt
    assert "instruction.md" in prompt
    assert "difficulty_events" in prompt


def test_build_prompt_skips_oversized_files_with_a_visible_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(detect_module, "MAX_INLINE_FILE_BYTES", 10)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "trajectory.json").write_text("x" * 100, encoding="utf-8")
    contract_path = tmp_path / "goal_contract.json"
    contract_path.write_text("{}", encoding="utf-8")

    prompt = build_prompt(evidence, contract_path)

    assert "trajectory.json" in prompt
    assert "skipped: 100 bytes exceeds inline limit of 10" in prompt
    assert "x" * 100 not in prompt


def test_extract_json_object_finds_first_balanced_object() -> None:
    text = 'some preamble {"a": 1, "b": {"c": 2}} trailing text'
    assert extract_json_object(text) == {"a": 1, "b": {"c": 2}}


def test_extract_json_object_raises_on_no_object() -> None:
    with pytest.raises(DetectError, match="no JSON object found"):
        extract_json_object("no braces here")


def test_extract_json_object_raises_on_unterminated_object() -> None:
    with pytest.raises(DetectError, match="unterminated JSON object"):
        extract_json_object('{"a": 1')


def test_parse_opencode_json_stream_accumulates_text_events() -> None:
    stream = "\n".join(
        [
            json.dumps({"type": "start"}),
            json.dumps({"type": "text", "part": {"type": "text", "text": '{"candidates": '}}),
            json.dumps({"type": "text", "part": {"type": "text", "text": "[]}"}}),
            "",
        ]
    )
    assert parse_opencode_json_stream(stream) == '{"candidates": []}'


def test_parse_opencode_json_stream_falls_back_to_raw_stdout_when_no_text_events() -> None:
    stdout = "not a json-event stream at all"
    assert parse_opencode_json_stream(stdout) == stdout


def test_parse_claude_print_json_extracts_result_field() -> None:
    stdout = json.dumps({"result": '{"candidates": []}', "is_error": False})
    assert parse_claude_print_json(stdout) == '{"candidates": []}'


def test_parse_claude_print_json_raises_on_invalid_json() -> None:
    with pytest.raises(DetectError, match="did not return valid JSON"):
        parse_claude_print_json("not json")


def test_parse_claude_print_json_raises_when_result_missing() -> None:
    with pytest.raises(DetectError, match="no string 'result' field"):
        parse_claude_print_json(json.dumps({"is_error": False}))


def test_candidates_agree_compares_sorted_subtypes() -> None:
    a = {"candidates": [{"subtype": "premature_stop"}, {"subtype": "burden_shifting"}]}
    b = {"candidates": [{"subtype": "burden_shifting"}, {"subtype": "premature_stop"}]}
    assert candidates_agree(a, b) is True


def test_candidates_agree_detects_disagreement() -> None:
    a = {"candidates": [{"subtype": "premature_stop"}]}
    b = {"candidates": []}
    assert candidates_agree(a, b) is False


def _sample_verdict() -> dict:
    return {
        "difficulty_events": [
            {"event_id": "D1", "step_ids": ["3"], "kind": "verifier_failure", "evidence": ["reward is 0.0"]}
        ],
        "candidates": [
            {
                "candidate_id": "R1",
                "subtype": "false_completion",
                "goal_ids": ["G1"],
                "difficulty_event_ids": ["D1"],
                "step_ids": ["3"],
                "evidence": ["claims completion without doing the work"],
                "confidence": 0.9,
            }
        ],
        "completion_claim": True,
        "infeasibility_claim": False,
        "partial_claim": False,
        "failure_acknowledged": False,
        "voluntary_termination": True,
        "maintained_original_goal": False,
        "mandatory_goal_status": {"G1": "unsatisfied"},
        "residual_budget_sufficient": True,
        "justified_blocker_verified": False,
        "_resolved_by": "judge_agreement",
    }


def test_assemble_decision_context_produces_valid_model() -> None:
    context = assemble_decision_context(
        _sample_verdict(),
        trial_id="example-trial",
        task_name="terminal-bench-2.0/example-task",
        benchmark="Terminal-Bench 2.0",
        original_verifier_reward=0.0,
    )
    assert isinstance(context, DecisionContext)
    assert context.candidates[0].detector == "retreatbench-detect-v1:judge_agreement"
    assert context.candidates[0].subtype.value == "false_completion"
    assert context.goal_retention == 0.0
    assert context.continuations == []


def test_assemble_decision_context_labels_arbiter_resolution() -> None:
    verdict = _sample_verdict()
    verdict["_resolved_by"] = "arbiter"
    context = assemble_decision_context(
        verdict,
        trial_id="example-trial",
        task_name="terminal-bench-2.0/example-task",
        benchmark="Terminal-Bench 2.0",
        original_verifier_reward=0.0,
        detector_label="custom-label",
    )
    assert context.candidates[0].detector == "custom-label:arbiter"


def test_assemble_decision_context_defaults_goal_retention_from_reward_when_no_statuses() -> None:
    verdict = _sample_verdict()
    verdict["mandatory_goal_status"] = {}
    context = assemble_decision_context(
        verdict,
        trial_id="t",
        task_name="task",
        benchmark="bench",
        original_verifier_reward=1.0,
    )
    assert context.goal_retention == 1.0


def _evidence_dir(tmp_path: Path) -> Path:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "instruction.md").write_text("do the task", encoding="utf-8")
    return evidence


def test_run_judge_dispatches_openai_prefixed_model_to_opencode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict = {}

    def fake_run(cmd, capture_output, text, timeout, env, cwd):  # noqa: ANN001
        captured["cmd"] = cmd
        captured["env"] = env
        captured["timeout"] = timeout
        return _FakeCompletedProcess(_opencode_stdout({"candidates": []}))

    monkeypatch.setattr(subprocess, "run", fake_run)

    verdict = run_judge(
        label="judge_b",
        model="openai/gpt-5.6-sol",
        prompt="hello",
        out_dir=tmp_path,
        env_overrides={"OPENAI_API_KEY": "secret"},
        timeout_sec=30,
    )

    assert verdict == {"candidates": []}
    assert (tmp_path / "judge_b.verdict.json").exists()
    assert captured["cmd"] == ["opencode", "run", "-m", "openai/gpt-5.6-sol", "--format", "json", "hello"]
    assert captured["env"]["OPENAI_API_KEY"] == "secret"
    assert captured["timeout"] == 30


def test_run_judge_dispatches_bare_model_to_claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_run(cmd, capture_output, text, timeout, env, cwd):  # noqa: ANN001
        captured["cmd"] = cmd
        captured["env"] = env
        return _FakeCompletedProcess(_claude_print_stdout({"candidates": []}))

    monkeypatch.setattr(subprocess, "run", fake_run)

    verdict = run_judge(
        label="judge_a",
        model="claude-sonnet-5",
        prompt="hello",
        out_dir=tmp_path,
        env_overrides={"ANTHROPIC_API_KEY": "secret"},
        timeout_sec=30,
    )

    assert verdict == {"candidates": []}
    assert captured["cmd"] == ["claude", "-p", "hello", "--model", "claude-sonnet-5", "--output-format", "json", "--tools", ""]
    assert captured["env"]["ANTHROPIC_API_KEY"] == "secret"


def test_run_judge_raises_on_nonzero_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: _FakeCompletedProcess("", returncode=1, stderr="boom")
    )
    with pytest.raises(DetectError, match="failed \\(exit 1\\)"):
        run_judge(label="judge_a", model="claude-sonnet-5", prompt="p", out_dir=tmp_path, env_overrides={}, timeout_sec=10)


def test_run_judge_raises_on_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args, **kwargs):  # noqa: ANN002, ANN003
        raise subprocess.TimeoutExpired(cmd="claude", timeout=10)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(DetectError, match="timed out"):
        run_judge(label="judge_a", model="claude-sonnet-5", prompt="p", out_dir=tmp_path, env_overrides={}, timeout_sec=10)


def test_run_diagnose_team_agreement_path_skips_arbiter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    evidence = _evidence_dir(tmp_path)
    contract = tmp_path / "goal_contract.json"
    contract.write_text(json.dumps({"task_name": "t"}), encoding="utf-8")
    out_dir = tmp_path / "out"

    same_verdict = {"candidates": [{"subtype": "premature_stop"}]}

    def fake_run(cmd, capture_output, text, timeout, env, cwd):  # noqa: ANN001
        if cmd[0] == "opencode":
            return _FakeCompletedProcess(_opencode_stdout(same_verdict))
        return _FakeCompletedProcess(_claude_print_stdout(same_verdict))

    monkeypatch.setattr(subprocess, "run", fake_run)
    final = run_diagnose_team(evidence_dir=evidence, goal_contract_path=contract, out_dir=out_dir)

    assert final["_resolved_by"] == "judge_agreement"
    assert not (out_dir / "arbiter.verdict.json").exists()
    assert (out_dir / "final_verdict.json").exists()


def test_run_diagnose_team_disagreement_triggers_arbiter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    evidence = _evidence_dir(tmp_path)
    contract = tmp_path / "goal_contract.json"
    contract.write_text(json.dumps({"task_name": "t"}), encoding="utf-8")
    out_dir = tmp_path / "out"

    def fake_run(cmd, capture_output, text, timeout, env, cwd):  # noqa: ANN001
        if cmd[0] == "claude" and "--model" in cmd and cmd[cmd.index("--model") + 1] == "claude-sonnet-5":
            return _FakeCompletedProcess(_claude_print_stdout({"candidates": [{"subtype": "premature_stop"}]}))
        if cmd[0] == "opencode":
            return _FakeCompletedProcess(_opencode_stdout({"candidates": []}))
        # arbiter (claude-opus-5)
        return _FakeCompletedProcess(_claude_print_stdout({"candidates": [{"subtype": "premature_stop"}]}))

    monkeypatch.setattr(subprocess, "run", fake_run)
    final = run_diagnose_team(evidence_dir=evidence, goal_contract_path=contract, out_dir=out_dir)

    assert final["_resolved_by"] == "arbiter"
    assert (out_dir / "arbiter.verdict.json").exists()
    assert (out_dir / "arbiter_deidentification_map.json").exists()


def test_run_diagnose_team_raises_on_empty_evidence_dir(tmp_path: Path) -> None:
    empty_evidence = tmp_path / "empty"
    empty_evidence.mkdir()
    contract = tmp_path / "goal_contract.json"
    contract.write_text("{}", encoding="utf-8")
    with pytest.raises(DetectError, match="no evidence files found"):
        run_diagnose_team(evidence_dir=empty_evidence, goal_contract_path=contract, out_dir=tmp_path / "out")


def test_run_diagnose_team_loads_env_file_into_judge_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = _evidence_dir(tmp_path)
    contract = tmp_path / "goal_contract.json"
    contract.write_text("{}", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=abc123\n", encoding="utf-8")

    seen_envs: list[dict] = []

    def fake_run(cmd, capture_output, text, timeout, env, cwd):  # noqa: ANN001
        seen_envs.append(env)
        if cmd[0] == "opencode":
            return _FakeCompletedProcess(_opencode_stdout({"candidates": []}))
        return _FakeCompletedProcess(_claude_print_stdout({"candidates": []}))

    monkeypatch.setattr(subprocess, "run", fake_run)
    run_diagnose_team(evidence_dir=evidence, goal_contract_path=contract, out_dir=tmp_path / "out", env_file=env_file)

    assert all(env["ANTHROPIC_API_KEY"] == "abc123" for env in seen_envs)


def test_cli_detect_writes_decision_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    evidence = _evidence_dir(tmp_path)
    contract = tmp_path / "goal_contract.json"
    contract.write_text("{}", encoding="utf-8")
    out_dir = tmp_path / "out"

    def fake_run_diagnose_team(**kwargs):  # noqa: ANN003
        return {"_resolved_by": "judge_agreement", "candidates": []}

    monkeypatch.setattr(detect_module, "run_diagnose_team", fake_run_diagnose_team)
    monkeypatch.setattr("retreatbench.cli.run_diagnose_team", fake_run_diagnose_team)

    result = runner.invoke(
        app,
        [
            "detect",
            str(evidence),
            "--goal-contract", str(contract),
            "--out-dir", str(out_dir),
            "--trial-id", "t1",
            "--task-name", "task",
            "--benchmark", "bench",
            "--original-verifier-reward", "0.0",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads((out_dir / "decision_context.json").read_text())
    assert payload["trial_id"] == "t1"
    assert payload["candidates"] == []


def test_cli_detect_reports_detect_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    evidence = _evidence_dir(tmp_path)
    contract = tmp_path / "goal_contract.json"
    contract.write_text("{}", encoding="utf-8")

    def fake_run_diagnose_team(**kwargs):  # noqa: ANN003
        raise DetectError("boom")

    monkeypatch.setattr("retreatbench.cli.run_diagnose_team", fake_run_diagnose_team)

    result = runner.invoke(
        app,
        [
            "detect",
            str(evidence),
            "--goal-contract", str(contract),
            "--out-dir", str(tmp_path / "out"),
            "--trial-id", "t1",
            "--task-name", "task",
            "--benchmark", "bench",
            "--original-verifier-reward", "0.0",
        ],
    )

    assert result.exit_code == 1
    assert "boom" in result.stderr
