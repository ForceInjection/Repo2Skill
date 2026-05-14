"""Extractor: rule-based candidate skill identification (Phase 1 prototype).

Scores skills from analysis.json by four criteria:
  - Recurrence: How often the function pattern appears
  - Verification: Whether the function has tests, docstrings, type hints
  - Non-obviousness: Complexity score (AST node count heuristic)
  - Generalizability: How parameterized/reusable the function is

Phase 1 uses deterministic rules only. LLM-based extraction arrives in Phase 3.
"""

from __future__ import annotations

import logging

from repo2skill.models import AnalysisResult, Skill, SkillCandidate

logger = logging.getLogger(__name__)

MAX_CANDIDATES = 5


def extract_skills(result: AnalysisResult) -> list[Skill]:
    """Score and rank candidate skills, returning the top 1–5.

    Skills are already pre-grouped by module from the structurer. This function
    scores each and selects the most promising candidates.
    """
    if not result.skills:
        return []

    scored = [_score_skill(s, result) for s in result.skills]

    # Sort by total score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Take top N
    top = scored[:MAX_CANDIDATES]

    # Log scores for debugging
    for total, skill, scores in top:
        logger.info(
            "Skill %s: total=%.2f rec=%.2f ver=%.2f nob=%.2f gen=%.2f cen=%.2f com=%.2f",
            skill.id,
            total,
            *scores,
        )

    return [skill for _, skill, _ in top]


def extract_skills_with_scores(result: AnalysisResult) -> list[SkillCandidate]:
    """Score and rank candidates, returning SkillCandidate objects with metadata.

    This provides baseline rule-based scoring. When an Agent (LLM) is available,
    the Agent can refine these scores by applying the 4 screening criteria
    (design.md §3.2) via reasoning, guided by SKILL.md instructions.

    Args:
        result: AnalysisResult from structure.py.

    Returns:
        List of SkillCandidate objects sorted by confidence descending.
    """
    if not result.skills:
        return []

    scored = [_score_skill(s, result) for s in result.skills]
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:MAX_CANDIDATES]

    candidates = []
    for total, skill, (rec, ver, nob, gen, cen, com) in top:
        # Normalize total (0–6 range) to confidence (0.0–1.0)
        confidence = min(total / 6.0, 1.0)

        # Build human-readable reasoning
        reasoning_parts = []
        if rec >= 0.7:
            reasoning_parts.append("rare pattern (high specialization value)")
        if ver >= 0.7:
            reasoning_parts.append("well-documented")
        if nob >= 0.5:
            reasoning_parts.append("high complexity (non-obvious)")
        if gen >= 0.5:
            reasoning_parts.append("highly reusable/parameterized")
        if cen >= 0.5:
            reasoning_parts.append("central (imported by many modules)")
        if com >= 0.7:
            reasoning_parts.append("comprehensively documented (high coverage)")

        candidate = SkillCandidate(
            id=skill.id,
            name=skill.name,
            description=skill.description,
            conditions=skill.conditions,
            policy=skill.policy,
            termination=skill.termination,
            interface=skill.interface,
            confidence=confidence,
            reasoning="; ".join(reasoning_parts) if reasoning_parts else "rule-based scoring",
            scores={
                "recurrence": round(rec, 2),
                "verification": round(ver, 2),
                "non_obviousness": round(nob, 2),
                "generalizability": round(gen, 2),
                "centrality": round(cen, 2),
                "completeness": round(com, 2),
                "total": round(total, 2),
            },
        )
        candidates.append(candidate)

    return candidates


def _score_skill(skill: Skill, result: AnalysisResult) -> tuple[float, Skill, tuple[float, ...]]:
    """Score a skill by six criteria. Returns (total, skill, (rec, ver, nob, gen, cen, com))."""
    rec = _score_recurrence(skill, result)
    ver = _score_verification(skill)
    nob = _score_non_obviousness(skill)
    gen = _score_generalizability(skill)
    cen = _score_centrality(skill, result)
    com = _score_completeness(skill)

    # Test-file penalty: multiply total by 0.7 for modules under tests/
    total = rec + ver + nob + gen + cen + com
    if _is_test_module(skill):
        total *= 0.7

    return (total, skill, (rec, ver, nob, gen, cen, com))


def _score_recurrence(skill: Skill, result: AnalysisResult) -> float:
    """Score 0.0–1.0 based on how many skills share similar patterns.

    A CLI entry point that appears once is more valuable (specialized knowledge).
    Functions with common patterns (many similar) score lower.
    """
    # Count how many skills have the same policy type
    same_type = sum(1 for s in result.skills if s.policy.type == skill.policy.type)
    total = max(len(result.skills), 1)

    # Rarer types score higher
    ratio = same_type / total
    if ratio <= 0.2:
        return 1.0
    if ratio <= 0.5:
        return 0.7
    if ratio <= 0.8:
        return 0.4
    return 0.1


def _score_verification(skill: Skill) -> float:
    """Score 0.0–1.0 based on documentation and type hint coverage.

    - Has docstring/trigger: +0.15 (reduced from 0.3 to avoid docstring-length bias)
    - Has file_patterns: +0.2
    - Has meaningful steps (>1): +0.3
    - Has params with type hints: +0.2
    - Penalty if steps are just template "Use X()" patterns: −0.15
    """
    score = 0.0

    if skill.conditions.triggers:
        score += 0.15

    if skill.conditions.file_patterns:
        score += 0.2

    steps = skill.policy.steps
    if steps and len(steps) > 1:
        # Penalize template "Use func()" steps — they carry no real information
        template_count = sum(1 for s in steps if s.startswith("Use ") and s.endswith("()"))
        if template_count >= len(steps) * 0.7:
            score += 0.15  # Reduced: mostly template steps
        else:
            score += 0.3   # Full credit: meaningful steps
    elif steps:
        score += 0.15

    typed_params = sum(1 for v in skill.interface.params.values() if v)
    total_params = max(len(skill.interface.params), 1)
    score += 0.2 * (typed_params / total_params)

    return min(score, 1.0)


def _score_non_obviousness(skill: Skill) -> float:
    """Score 0.0–1.0 based on complexity signals.

    Higher complexity = more value in having a skill document it.
    """
    score = 0.0

    # Number of steps as a complexity proxy
    step_count = len(skill.policy.steps)
    if step_count >= 5:
        score += 0.5
    elif step_count >= 3:
        score += 0.3
    elif step_count >= 1:
        score += 0.1

    # Number of dependencies
    dep_count = len(skill.policy.dependencies)
    if dep_count >= 4:
        score += 0.3
    elif dep_count >= 2:
        score += 0.2
    elif dep_count >= 1:
        score += 0.1

    # Number of preconditions
    if len(skill.conditions.preconditions) >= 2:
        score += 0.2
    elif len(skill.conditions.preconditions) >= 1:
        score += 0.1

    return min(score, 1.0)


def _score_generalizability(skill: Skill) -> float:
    """Score 0.0–1.0 based on how parameterized and reusable the skill is."""
    score = 0.0

    param_count = len(skill.interface.params)
    if param_count >= 4:
        score += 0.5
    elif param_count >= 2:
        score += 0.3
    elif param_count >= 1:
        score += 0.1

    # File patterns suggest broader applicability
    if skill.conditions.file_patterns:
        score += 0.2

    # "function" type is more reusable than "script"
    if skill.policy.type == "function":
        score += 0.3
    elif skill.policy.type == "workflow":
        score += 0.2

    return min(score, 1.0)


def _score_centrality(skill: Skill, result: AnalysisResult) -> float:
    """Score 0.0–1.0 based on how many other modules import this module.

    A module imported by many others is a core dependency — its skill is more
    valuable to document. Modules with 0 incoming edges (leaf nodes) get 0.0.
    The score is normalized against the max in-degree in the graph.
    """
    dep_graph = result.dependency_graph
    if not dep_graph or not dep_graph.get("edges"):
        return 0.0

    entry = skill.policy.entry
    if not entry:
        return 0.0

    # Extract the module prefix from the entry (everything before last dot)
    entry_module = entry.rsplit(".", 1)[0] if "." in entry else entry

    # Candidate node names to match (both file-path and package naming conventions)
    candidates = {entry_module}
    for prefix in ("src.", "tests."):
        if entry_module.startswith(prefix):
            candidates.add(entry_module[len(prefix):])
        else:
            candidates.add(f"{prefix}{entry_module}")

    # Count incoming edges (other→this module)
    in_degree = 0
    max_in_degree = 1
    in_degrees: dict[str, int] = {}
    for edge in dep_graph.get("edges", []):
        tgt = edge.get("target", "")
        in_degrees[tgt] = in_degrees.get(tgt, 0) + 1
        if tgt in candidates:
            in_degree += 1
        max_in_degree = max(max_in_degree, in_degrees.get(tgt, 0))

    if max_in_degree <= 1:
        return 0.5 if in_degree > 0 else 0.0

    return min(in_degree / max_in_degree, 1.0)


def _is_test_module(skill: Skill) -> bool:
    """Check if a skill comes from a test module.

    Test modules typically start with 'tests.' or contain '.test_' or
    end with '_test'. The entry point path reveals the module origin.
    """
    entry = skill.policy.entry.lower()
    return (
        entry.startswith("tests.")
        or ".test_" in entry
        or entry.endswith("_test")
    )


def _score_completeness(skill: Skill) -> float:
    """Score 0.0–1.0 based on documentation completeness (feature coverage).

    Measures how thoroughly the skill is documented across all four-tuple
    dimensions (paper §7 "Completeness / Feature Coverage"):

    - Parameter type coverage: typed_params / total_params (0.0–0.3)
    - Trigger/documentation coverage: has triggers + docstring (0.0–0.3)
    - Termination criteria defined (0.0–0.2)
    - Steps beyond template "Use X()" patterns (0.0–0.2)
    """
    score = 0.0

    # Parameter type coverage
    total_params = len(skill.interface.params)
    if total_params > 0:
        typed = sum(1 for v in skill.interface.params.values() if v)
        score += 0.3 * (typed / total_params)

    # Trigger and docstring coverage
    if skill.conditions.triggers:
        score += 0.15
    if skill.description:
        score += 0.15

    # Termination criteria
    if skill.termination.success:
        score += 0.2

    # Meaningful steps (not just "Use X()" templates)
    steps = skill.policy.steps
    if steps:
        meaningful = sum(1 for s in steps
                        if not (s.startswith("Use ") and s.endswith("()")))
        score += 0.2 * min(meaningful / max(len(steps), 1), 1.0)

    return min(score, 1.0)
