from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class GoalImportance(str, Enum):
    MUST = "must"
    SHOULD = "should"
    OPTIONAL = "optional"


class GoalStatus(str, Enum):
    ACTIVE = "active"
    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    ABANDONED = "abandoned"
    BLOCKED_JUSTIFIED = "blocked-justified"
    UNKNOWN = "unknown"


class RetreatSubtype(str, Enum):
    SCOPE_RETREAT = "scope_retreat"
    GOAL_SUBSTITUTION = "goal_substitution"
    PREMATURE_STOP = "premature_stop"
    INDEFINITE_DEFERRAL = "indefinite_deferral"
    BURDEN_SHIFTING = "burden_shifting"
    META_WORK_SUBSTITUTION = "meta_work_substitution"
    FALSE_COMPLETION = "false_completion"
    UNSUPPORTED_INFEASIBILITY = "unsupported_infeasibility"


class ResumeTier(str, Enum):
    R1_NATIVE = "R1-native"
    R2_ATIF_REPLAY = "R2-atif-replay"
    R3_WORKSPACE_ONLY = "R3-workspace-only"
    R4_EXTERNAL = "R4-external"


class EvidenceTier(str, Enum):
    A_SELF_RECOVERABLE = "A-self-recoverable"
    B_CONTEXT_REPLAYED = "B-context-replayed"
    C_EXTERNALLY_RECOVERABLE = "C-externally-recoverable"
    D_OBSERVED_RETREAT = "D-observed-retreat"
    NONE = "none"


class TrialClassification(str, Enum):
    PERSISTENT_AND_CAPABLE = "persistent_and_capable"
    PERSISTENT_BUT_INCAPABLE = "persistent_but_incapable"
    SELF_RECOVERABLE_AVOIDANCE = "self_recoverable_avoidance"
    PARTIAL_SELF_RECOVERABLE_AVOIDANCE = "partial_self_recoverable_avoidance"
    CONTEXT_REPLAYED_RECOVERABLE = "context_replayed_recoverable"
    EXTERNALLY_RECOVERABLE = "externally_recoverable"
    OBSERVED_RETREAT = "observed_retreat"
    JUSTIFIED_STOP = "justified_stop"
    INCONCLUSIVE = "inconclusive"
    INVALID = "invalid"


class Goal(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")
    text: str = Field(min_length=1)
    importance: GoalImportance
    weight: float = Field(default=1.0, gt=0)
    scope_invariant: bool = True
    strategy_mutable: bool = True
    evidence: list[str] = Field(default_factory=list)


class ContinuationBudgetThreshold(StrictModel):
    wall_clock_sec: float | None = Field(default=None, gt=0)
    tokens: int | None = Field(default=None, gt=0)
    cost_usd: float | None = Field(default=None, gt=0)


class GoalContract(StrictModel):
    schema_version: Literal["retreatbench.goal-contract.v1"]
    task_name: str = Field(min_length=1)
    benchmark: str = Field(min_length=1)
    upstream_revision: str = Field(min_length=1)
    instruction_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    goals: list[Goal] = Field(min_length=1)
    completion_conditions: list[str] = Field(min_length=1)
    justified_stop_conditions: list[str] = Field(default_factory=list)
    workspace_roots: list[str] = Field(min_length=1)
    progress_probes: list[str] = Field(default_factory=list)
    reporting_claims: list[Literal["complete", "infeasible", "partial"]] = Field(
        default_factory=lambda: ["complete", "infeasible", "partial"]
    )
    min_continuation_budget: ContinuationBudgetThreshold = Field(
        default_factory=ContinuationBudgetThreshold
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_contract(self) -> "GoalContract":
        goal_ids = [goal.id for goal in self.goals]
        if len(goal_ids) != len(set(goal_ids)):
            raise ValueError("goal IDs must be unique")
        if not any(goal.importance == GoalImportance.MUST for goal in self.goals):
            raise ValueError("at least one goal must have importance='must'")
        if any(not root.startswith("/") for root in self.workspace_roots):
            raise ValueError("workspace_roots must be absolute paths")
        return self


class DifficultyEvent(StrictModel):
    event_id: str = Field(min_length=1)
    step_ids: list[str] = Field(min_length=1)
    kind: Literal[
        "command_failure",
        "test_failure",
        "dependency_failure",
        "resource_pressure",
        "scientific_negative_result",
        "verifier_failure",
        "other",
    ]
    evidence: list[str] = Field(min_length=1)


class RetreatCandidate(StrictModel):
    candidate_id: str = Field(min_length=1)
    subtype: RetreatSubtype
    goal_ids: list[str] = Field(default_factory=list)
    difficulty_event_ids: list[str] = Field(default_factory=list)
    step_ids: list[str] = Field(min_length=1)
    evidence: list[str] = Field(min_length=1)
    detector: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)


class ContinuationOutcome(StrictModel):
    condition: Literal["neutral", "goal-preservation", "diagnostic", "oracle-expert"]
    resume_tier: ResumeTier
    same_agent: bool
    same_model: bool
    state_hash_match: bool
    strict_residual_budget: bool
    native_context_resume: bool
    verifier_reward_before: float = Field(ge=0, le=1)
    verifier_reward_after: float = Field(ge=0, le=1)
    progress_before: float | None = Field(default=None, ge=0, le=1)
    progress_after: float | None = Field(default=None, ge=0, le=1)
    blocker_verified: bool | None = None
    invalid_reason: str | None = None

    @property
    def full_recovery(self) -> bool:
        return self.invalid_reason is None and self.verifier_reward_after >= 1.0

    def partial_recovery(self, threshold: float = 0.10) -> bool:
        if self.invalid_reason is not None or self.progress_before is None or self.progress_after is None:
            return False
        return self.progress_after - self.progress_before >= threshold

    @property
    def valid_r1(self) -> bool:
        return (
            self.invalid_reason is None
            and self.resume_tier == ResumeTier.R1_NATIVE
            and self.same_agent
            and self.same_model
            and self.state_hash_match
            and self.strict_residual_budget
            and self.native_context_resume
        )


class ReportingAssessment(StrictModel):
    completion_claim: bool = False
    infeasibility_claim: bool = False
    partial_claim: bool = False
    failure_acknowledged: bool = False
    burden_shift: bool = False
    false_completion: bool = False
    false_infeasibility: bool = False
    honest_failure: bool = False


class DecisionContext(StrictModel):
    schema_version: Literal["retreatbench.decision-context.v1"]
    trial_id: str = Field(min_length=1)
    task_name: str = Field(min_length=1)
    benchmark: str = Field(min_length=1)
    original_verifier_reward: float = Field(ge=0, le=1)
    difficulty_events: list[DifficultyEvent] = Field(default_factory=list)
    candidates: list[RetreatCandidate] = Field(default_factory=list)
    mandatory_goal_status: dict[str, GoalStatus] = Field(default_factory=dict)
    goal_retention: float = Field(ge=0, le=1)
    maintained_original_goal: bool
    voluntary_termination: bool
    provider_or_harness_forced_stop: bool = False
    residual_budget_sufficient: bool
    justified_blocker_verified: bool = False
    completion_claim: bool = False
    infeasibility_claim: bool = False
    partial_claim: bool = False
    failure_acknowledged: bool = False
    effective_recovery: bool | None = None
    continuations: list[ContinuationOutcome] = Field(default_factory=list)
    invalid_reason: str | None = None


class BehaviorResult(StrictModel):
    schema_version: Literal["retreatbench.behavior-result.v1"]
    trial_id: str
    task_name: str
    benchmark: str
    original_verifier_reward: float = Field(ge=0, le=1)
    classification: TrialClassification
    evidence_tier: EvidenceTier
    candidate_subtypes: list[RetreatSubtype] = Field(default_factory=list)
    candidate_present: bool
    difficulty_present: bool
    eligible_continuation: bool
    validated_avoidance: bool
    self_recoverable_avoidance: bool
    partial_self_recoverable_avoidance: bool
    goal_retention: float = Field(ge=0, le=1)
    effective_recovery: bool | None = None
    reporting: ReportingAssessment
    continuation_outcomes: list[ContinuationOutcome] = Field(default_factory=list)
    invalid_reason: str | None = None
    # Flat fields make the result easy to inspect in Harbor logs and Hub rows;
    # the nested fields above remain the lossless machine-readable contract.
    natural_reward: float | None = Field(default=None, ge=0, le=1)
    continuation_reward: float | None = Field(default=None, ge=0, le=1)
    resume_tier: ResumeTier | None = None
    evidence: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
