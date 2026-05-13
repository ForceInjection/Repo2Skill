#!/usr/bin/env python3
"""Thin CLI wrapper: render templates and assemble skill directory.

Usage:
    python assemble.py <analysis.json> <selected_ids> <output_dir> [--mode suite]

selected_ids is a comma-separated list of skill IDs (e.g., "sk1,sk3").
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from repo2skill.models import AnalysisResult, Skill, SuiteConfig
from repo2skill.suite import assemble_suite, infer_relations, validate_dag


def main() -> None:
    if len(sys.argv) < 4:
        print(
            "Usage: python assemble.py <analysis.json> <selected_ids> <output_dir> [--mode suite]",
            file=sys.stderr,
        )
        sys.exit(1)

    analysis_path = Path(sys.argv[1])
    selected_ids = [s.strip() for s in sys.argv[2].split(",")]
    output_dir = Path(sys.argv[3])
    output_dir.mkdir(parents=True, exist_ok=True)

    mode = "single"
    if len(sys.argv) >= 5 and sys.argv[4] == "--mode":
        mode = sys.argv[5] if len(sys.argv) >= 6 else "single"

    if not analysis_path.exists():
        print(f"Error: {analysis_path} not found.", file=sys.stderr)
        sys.exit(1)

    # Load analysis result
    data = json.loads(analysis_path.read_text(encoding="utf-8"))
    result = AnalysisResult(**data)

    # Find selected skills
    selected = [s for s in result.skills if s.id in selected_ids]
    if not selected:
        print(f"Error: none of {selected_ids} found in analysis.json", file=sys.stderr)
        sys.exit(1)

    source = data.get("repo", "")

    if mode == "suite" and len(selected) > 1:
        # Suite mode
        relations = infer_relations(selected, result.dependency_graph)
        valid, dag_msg = validate_dag(relations)
        if not valid:
            print(f"Warning: {dag_msg}")

        suite_config = SuiteConfig(
            name=result.repo,
            description=f"Skill suite for {result.repo}",
            skills=[s.id for s in selected],
            relations=relations,
        )
        suite_dir = assemble_suite(suite_config, selected, output_dir, source=source, trust_level="L0")
        print(f"Assembled skill suite at: {suite_dir}")
    else:
        # Single mode
        from repo2skill.assemble import assemble_skill

        for skill in selected:
            skill_dir = assemble_skill(skill, output_dir, source=source)
            print(f"Assembled skill at: {skill_dir}")


if __name__ == "__main__":
    main()
