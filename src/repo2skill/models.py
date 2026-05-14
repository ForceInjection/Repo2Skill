"""Four-tuple skill data models matching design.md §12.1."""

from pydantic import BaseModel, Field


class Conditions(BaseModel):
    """C — Applicable conditions and trigger scenarios."""

    triggers: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    file_patterns: list[str] = Field(default_factory=list)

    @property
    def trigger(self) -> str:
        """Backward-compat: return the first trigger pattern, or empty string."""
        return self.triggers[0] if self.triggers else ""


class Policy(BaseModel):
    """π — Core strategy and action sequence."""

    type: str = ""  # "script" | "function" | "workflow"
    entry: str = ""  # e.g. "black.main"
    steps: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class Termination(BaseModel):
    """T — Termination criteria and success determination."""

    success: str = ""
    output_schema: dict = Field(default_factory=dict)


class Interface(BaseModel):
    """R — Standardized invocation interface."""

    params: dict = Field(default_factory=dict)
    allowed_tools: list[str] = Field(
        default_factory=list,
        serialization_alias="allowed-tools",
    )


class Skill(BaseModel):
    """A single candidate skill with four-tuple decomposition."""

    id: str  # e.g. "sk1"
    name: str = ""
    description: str = ""
    conditions: Conditions = Field(default_factory=Conditions)
    policy: Policy = Field(default_factory=Policy)
    termination: Termination = Field(default_factory=Termination)
    interface: Interface = Field(default_factory=Interface)


class SkillCandidate(Skill):
    """A skill candidate with scoring metadata from the Extractor (design.md §3.2).

    Extends Skill with confidence, reasoning, and per-criterion scores
    produced by either rule-based scoring or Agent (LLM) reasoning.
    """

    confidence: float = 0.0  # 0.0–1.0 overall confidence
    reasoning: str = ""  # human-readable explanation of selection
    scores: dict[str, float] = Field(default_factory=dict)  # per-criterion scores


class AnalysisResult(BaseModel):
    """Top-level output of structure.py — consumed by extractor and assembler."""

    repo: str
    skills: list[Skill] = Field(default_factory=list)
    dependency_graph: dict = Field(default_factory=dict)
    readme_summary: str = ""  # first 4000 chars of README for Agent context


class G1Report(BaseModel):
    """G1 static security scan report (design.md §4.2)."""

    skill_name: str = ""
    passed: bool = True  # no blocking findings
    findings: list[dict] = Field(default_factory=list)
    vulnerability_rate: float = 0.0  # design.md §7: 存在风险的技能占比
    # finding dict: {"pattern": str, "file": str, "line": int, "severity": "high"|"medium"|"low"}


class G2Report(BaseModel):
    """G2 semantic review report (design.md §4.3).

    Produced by the Agent (LLM reasoning), not by deterministic scripts.
    """

    skill_name: str = ""
    score: float = 0.0  # 0.0–1.0, see design.md Table 4.3
    verdict: str = ""  # "complete" | "partial" | "questionable"
    hallucination_check: str = ""
    injection_check: str = ""
    metadata_consistency: str = ""
    recommendations: list[str] = Field(default_factory=list)


class SuiteConfig(BaseModel):
    """Configuration for a Skill Suite (design.md §2.5)."""

    name: str = ""
    description: str = ""
    skills: list[str] = Field(default_factory=list)  # skill IDs in this suite
    relations: list[dict] = Field(default_factory=list)
    # relation dict: {"source": str, "target": str, "type": "depends-on"|"composes"|"bundled-with"|"requires-output-from"}
