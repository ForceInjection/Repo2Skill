"""Skill Suite detection and assembly (design.md §2.5).

Detects when a repo should be split into multiple skills instead of a single
monolithic skill. Provides DAG validation for inter-skill relations.

Suite mode is triggered when any of these conditions hold:
  1. Candidate count > 1 AND combined Level 2 > 4,000 tokens
  2. Multiple entry points (distinct CLI/public API surfaces)
  3. Disconnected dependency clusters
  4. Divergent allowed-tools across candidates
"""

from __future__ import annotations

import logging
from pathlib import Path

from repo2skill.models import Skill, SkillCandidate, SuiteConfig, AnalysisResult

logger = logging.getLogger(__name__)

# Token budget threshold for suite detection (design.md §2.5)
SUITE_TOKEN_THRESHOLD = 4000
# Disconnected cluster threshold
MIN_CLUSTER_SIZE = 2


def detect_suite_mode(
    result: AnalysisResult,
    candidates: list[Skill] | list[SkillCandidate],
) -> tuple[bool, str]:
    """Determine whether the repo should be decomposed into a Skill Suite.

    Applies the 4 screening criteria from design.md §2.5.

    Args:
        result: The analysis result with dependency graph.
        candidates: Candidate skills to evaluate.

    Returns:
        (is_suite, reason) tuple.
    """
    if len(candidates) <= 1:
        return False, "Only one candidate — single skill mode"

    reasons: list[str] = []

    # Criterion 1: Combined Level 2 token budget > 4,000
    combined_body_tokens = _estimate_combined_tokens(candidates)
    if combined_body_tokens > SUITE_TOKEN_THRESHOLD:
        reasons.append(
            f"Combined Level 2 body exceeds {SUITE_TOKEN_THRESHOLD} tokens "
            f"(estimated {combined_body_tokens})"
        )

    # Criterion 2: Multiple entry points (distinct policy types)
    entry_types = {c.policy.type for c in candidates if c.policy.type}
    if len(entry_types) > 1:
        reasons.append(
            f"Multiple entry-point types detected: {', '.join(sorted(entry_types))}"
        )

    # Criterion 3: Disconnected dependency clusters
    clusters = find_disconnected_clusters(result.dependency_graph)
    if len(clusters) >= MIN_CLUSTER_SIZE:
        reasons.append(
            f"Found {len(clusters)} disconnected dependency clusters"
        )

    # Criterion 4: Divergent allowed-tools
    tool_sets = _group_by_tools(candidates)
    if len(tool_sets) > 1:
        reasons.append(
            f"Divergent allowed-tools across candidates ({len(tool_sets)} distinct tool sets)"
        )

    is_suite = len(reasons) >= 1
    reason = "; ".join(reasons) if reasons else "No suite criteria met"
    return is_suite, reason


def _estimate_combined_tokens(candidates: list[Skill] | list[SkillCandidate]) -> int:
    """Estimate combined Level 2 token count for all candidates."""
    total = 0
    for c in candidates:
        # Rough estimate: steps + description + entry + conditions
        text = (
            c.description
            + " ".join(c.policy.steps)
            + " ".join(c.policy.dependencies)
            + c.conditions.trigger
            + " ".join(c.conditions.preconditions)
        )
        total += len(text) // 4  # ~4 chars per token
    return total


def _group_by_tools(candidates: list[Skill] | list[SkillCandidate]) -> dict:
    """Group candidates by their allowed-tools signatures."""
    groups: dict[str, list] = {}
    for c in candidates:
        key = ",".join(sorted(c.interface.allowed_tools))
        groups.setdefault(key, []).append(c.id)
    return groups


def find_disconnected_clusters(dep_graph: dict) -> list[list[str]]:
    """Find disconnected subgraphs in the dependency graph.

    Uses BFS to find connected components. A cluster is a set of nodes
    with no edges connecting to other clusters.

    Args:
        dep_graph: Dependency graph with 'nodes' and 'edges' keys.

    Returns:
        List of clusters, each being a list of node names.
    """
    nodes = dep_graph.get("nodes", [])
    if not nodes:
        return []

    # Build adjacency list (undirected for connectivity)
    adj: dict[str, set[str]] = {n: set() for n in nodes}
    for edge in dep_graph.get("edges", []):
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src in adj and tgt in adj:
            adj[src].add(tgt)
            adj[tgt].add(src)

    visited: set[str] = set()
    clusters: list[list[str]] = []

    for node in nodes:
        if node in visited:
            continue
        # BFS
        cluster: list[str] = []
        queue = [node]
        visited.add(node)
        while queue:
            current = queue.pop(0)
            cluster.append(current)
            for neighbor in adj.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        clusters.append(sorted(cluster))

    return clusters


def infer_relations(
    candidates: list[Skill] | list[SkillCandidate],
    dep_graph: dict,
) -> list[dict]:
    """Infer inter-skill relations from candidates and dependency graph.

    Returns list of relation dicts with keys:
      - source: source skill ID
      - target: target skill ID
      - type: "depends-on" | "composes" | "bundled-with" | "requires-output-from"
    """
    relations: list[dict] = []
    skill_ids = {c.id for c in candidates}

    edges = dep_graph.get("edges", [])
    skill_deps: dict[str, set[str]] = {}

    # Map modules to skill IDs
    for c in candidates:
        module = c.policy.entry.split(".")[0] if c.policy.entry else ""
        skill_deps.setdefault(c.id, set())

    # Infer depends-on from dependency graph
    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        src_skill = _find_skill_for_module(candidates, src)
        tgt_skill = _find_skill_for_module(candidates, tgt)
        if src_skill and tgt_skill and src_skill != tgt_skill:
            already_exists = any(
                r["source"] == src_skill
                and r["target"] == tgt_skill
                and r["type"] == "depends-on"
                for r in relations
            )
            if not already_exists:
                relations.append(
                    {
                        "source": src_skill,
                        "target": tgt_skill,
                        "type": "depends-on",
                    }
                )

    # Infer composes: if one skill's steps reference another skill's entry
    for c1 in candidates:
        for c2 in candidates:
            if c1.id == c2.id:
                continue
            if c2.policy.entry and c2.policy.entry in " ".join(c1.policy.steps):
                already_exists = any(
                    r["source"] == c1.id
                    and r["target"] == c2.id
                    and r["type"] == "composes"
                    for r in relations
                )
                if not already_exists:
                    relations.append(
                        {"source": c1.id, "target": c2.id, "type": "composes"}
                    )

    # Infer bundled-with: same allowed-tools and same policy type
    for i, c1 in enumerate(candidates):
        for c2 in candidates[i + 1 :]:
            if (
                c1.policy.type == c2.policy.type
                and set(c1.interface.allowed_tools) == set(c2.interface.allowed_tools)
            ):
                already_exists = any(
                    r["source"] == c1.id
                    and r["target"] == c2.id
                    and r["type"] == "bundled-with"
                    for r in relations
                )
                if not already_exists:
                    relations.append(
                        {"source": c1.id, "target": c2.id, "type": "bundled-with"}
                    )

    return relations


def _find_skill_for_module(
    candidates: list[Skill] | list[SkillCandidate], module: str
) -> str | None:
    """Find the skill ID that corresponds to a given module name.

    Uses exact match first, then prefix match against module boundaries.
    """
    # First pass: exact match on the module portion of entry
    for c in candidates:
        entry = c.policy.entry
        if entry:
            entry_module = entry.split(".")[0]
            if entry_module == module:
                return c.id

    # Second pass: prefix match (e.g., "module.sub" matching "module.sub.func")
    for c in candidates:
        entry = c.policy.entry
        if entry and entry.startswith(module + "."):
            return c.id

    return None


def validate_dag(relations: list[dict]) -> tuple[bool, str]:
    """Validate that inter-skill relations form a DAG (no cycles).

    Only checks depends-on relations for cycles, since composes and
    bundled-with are not directional dependencies.

    Args:
        relations: List of relation dicts.

    Returns:
        (is_valid, message) tuple.
    """
    # Build adjacency for depends-on only
    deps: dict[str, set[str]] = {}
    nodes: set[str] = set()

    for r in relations:
        src = r["source"]
        tgt = r["target"]
        nodes.add(src)
        nodes.add(tgt)
        if r["type"] == "depends-on":
            deps.setdefault(src, set()).add(tgt)
        elif r["type"] == "requires-output-from":
            deps.setdefault(src, set()).add(tgt)

    # DFS cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n: WHITE for n in nodes}

    def dfs(node: str) -> bool:
        """Return True if a cycle is found."""
        color[node] = GRAY
        for neighbor in deps.get(node, set()):
            if color.get(neighbor, WHITE) == GRAY:
                return True
            if color.get(neighbor, WHITE) == WHITE:
                if dfs(neighbor):
                    return True
        color[node] = BLACK
        return False

    for node in nodes:
        if color[node] == WHITE:
            if dfs(node):
                return False, f"Cycle detected involving node: {node}"

    return True, "DAG is valid — no cycles detected"


def assemble_suite(
    suite_config: SuiteConfig,
    candidates: list[Skill] | list[SkillCandidate],
    output_dir: Path,
    source: str = "",
    version: str = "0.1.0",
    trust_level: str = "L1",
) -> Path:
    """Create a Skill Suite directory with suite.yaml and per-skill subdirectories.

    Args:
        suite_config: Suite configuration with name, description, skills, relations.
        candidates: All candidate skills.
        output_dir: Parent output directory.
        source: Original repo source URL/path.
        version: Version string.
        trust_level: Trust level for the suite (default L1 from G1 scan).

    Returns:
        Path to the created suite directory.
    """
    from jinja2 import Environment, FileSystemLoader

    from repo2skill.assemble import assemble_skill

    # Create suite directory (sanitize name)
    suite_name = _sanitize_dirname(suite_config.name)
    suite_dir = output_dir / f"{suite_name}-suite"
    suite_dir.mkdir(parents=True, exist_ok=True)

    # Render suite.yaml
    template_dir = Path(__file__).resolve().parent.parent.parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=False,
        keep_trailing_newline=True,
    )

    ctx = {
        "name": suite_config.name,
        "description": suite_config.description,
        "version": version,
        "source": source,
        "trust_level": trust_level,
        "skills": [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "path": f"./{_sanitize_dirname(s.name)}-skill/",
            }
            for s in candidates
        ],
        "relations": suite_config.relations,
    }

    suite_yaml_template = env.get_template("suite.yaml.j2")
    suite_yaml_content = suite_yaml_template.render(**ctx)
    (suite_dir / "suite.yaml").write_text(suite_yaml_content, encoding="utf-8")
    logger.info("Wrote %s/suite.yaml", suite_dir)

    # Generate README.md (design.md §4)
    _write_suite_readme(suite_dir, suite_config, candidates, source)

    # Create suite-level verification directory
    (suite_dir / "verification").mkdir(exist_ok=True)

    # Assemble each skill into its own subdirectory
    skill_map = {c.id: c for c in candidates}
    for skill_id in suite_config.skills:
        if skill_id in skill_map:
            skill = skill_map[skill_id]
            # Convert SkillCandidate to Skill if needed
            if isinstance(skill, SkillCandidate):
                base_skill = Skill(
                    id=skill.id,
                    name=skill.name,
                    description=skill.description,
                    conditions=skill.conditions,
                    policy=skill.policy,
                    termination=skill.termination,
                    interface=skill.interface,
                )
            else:
                base_skill = skill
            # Compute per-skill ontology relations
            skill_relations = [
                {"type": r["type"], "target": r["target"]}
                for r in suite_config.relations
                if r["source"] == skill_id
            ]
            assemble_skill(
                base_skill, suite_dir, source=source, version=version,
                ontology_relations=skill_relations,
            )

    logger.info("Assembled skill suite at %s", suite_dir)
    return suite_dir


def _sanitize_dirname(name: str) -> str:
    """Collapse non-alphanumeric sequences into a single hyphen."""
    import re
    sanitized = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return sanitized


def _write_suite_readme(
    suite_dir: Path,
    suite_config: SuiteConfig,
    candidates: list[Skill] | list[SkillCandidate],
    source: str,
) -> None:
    """Generate a human-readable README.md for the suite (design.md §4)."""
    lines = [
        f"# {suite_config.name} — Skill Suite",
        "",
        f"{suite_config.description}.",
        "",
        f"**Source**: {source}",
        f"**Skills**: {len(candidates)}",
        "",
        "## Skills",
        "",
    ]
    for c in candidates:
        safe_name = c.name.lower().replace(" ", "-").replace("_", "-")
        lines.append(f"- **[{c.id}] {c.name}** — {c.description}")
        lines.append(f"  - Entry: `{c.policy.entry}`")
        lines.append(f"  - Type: {c.policy.type}")
        lines.append(f"  - Path: `./{safe_name}-skill/`")
        lines.append("")

    if suite_config.relations:
        lines.append("## Relations")
        lines.append("")
        for r in suite_config.relations:
            lines.append(f"- `{r['source']}` → `{r['target']}` ({r['type']})")
        lines.append("")

    lines.append("## Usage")
    lines.append("")
    lines.append("Load any sub-skill individually, or load the suite to make all skills available.")
    lines.append("")

    (suite_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote %s/README.md", suite_dir)
