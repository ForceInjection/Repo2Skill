#!/usr/bin/env python3
"""Thin CLI wrapper: run rule-based extraction and write candidates for Agent review.

Usage:
    python extract.py <analysis.json> <output_dir>

Writes `candidates.json` with SkillCandidate objects (rule-based baseline scores).
The Agent reads this and applies LLM reasoning to refine the results.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from repo2skill.models import AnalysisResult


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python extract.py <analysis.json> <output_dir>", file=sys.stderr)
        sys.exit(1)

    analysis_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)

    if not analysis_path.exists():
        print(f"Error: {analysis_path} not found. Run structure.py first.", file=sys.stderr)
        sys.exit(1)

    # Load analysis result
    data = json.loads(analysis_path.read_text(encoding="utf-8"))
    result = AnalysisResult(**data)

    from repo2skill.extractor import extract_skills_with_scores

    candidates = extract_skills_with_scores(result)

    # Write candidates for Agent to read and refine
    candidates_json = json.dumps(
        [c.model_dump() for c in candidates],
        indent=2,
        ensure_ascii=False,
    )
    candidates_path = output_dir / "candidates.json"
    candidates_path.write_text(candidates_json, encoding="utf-8")

    print(f"Wrote {len(candidates)} candidate(s) to {candidates_path}")
    print("\nIMPORTANT: These are rule-based HINTS only.")
    print("The Agent MUST read the FULL analysis.json (all functions, not just top 5)")
    print("and independently filter, merge, score, and enrich candidates.")
    print("See SKILL.md Extractor section (Steps A-E) for the complete workflow.")
    print("\nCandidate summary (rule-based hints):")
    for c in candidates:
        print(f"  [{c.id}] {c.name} (confidence: {c.confidence:.2f}) — {c.reasoning}")


if __name__ == "__main__":
    main()
