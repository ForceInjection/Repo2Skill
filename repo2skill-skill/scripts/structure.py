#!/usr/bin/env python3
"""Thin CLI wrapper: run the Structurer and write analysis.json.

Usage:
    python structure.py <source> <output_dir>

The Agent invokes this via Bash, then reads analysis.json to act as Extractor.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running from a deployed skill directory where the `repo2skill` package
# is vendored as a sibling of `scripts/`. In dev mode (pip install -e .) the
# installed package is found first and this path entry is harmless.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python structure.py <source> <output_dir>", file=sys.stderr)
        sys.exit(1)

    source = sys.argv[1]
    output_dir = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)

    from repo2skill.structure import analyze_repo

    print(f"Analyzing: {source}")
    result = analyze_repo(source)

    analysis_path = output_dir / "analysis.json"
    analysis_path.write_text(result.model_dump_json(indent=2, by_alias=True), encoding="utf-8")
    print(f"Wrote analysis.json ({len(result.skills)} skills, "
          f"{len(result.dependency_graph.get('nodes', []))} modules)")


if __name__ == "__main__":
    main()
