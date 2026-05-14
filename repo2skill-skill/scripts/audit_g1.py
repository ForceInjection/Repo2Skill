#!/usr/bin/env python3
"""Thin CLI wrapper: run G1 static security scan on a skill directory.

Usage:
    python audit_g1.py <skill_dir>

Writes g1_report.json next to the skill directory.
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
    if len(sys.argv) < 2:
        print("Usage: python audit_g1.py <skill_dir>", file=sys.stderr)
        sys.exit(1)

    skill_dir = Path(sys.argv[1])

    if not skill_dir.exists() or not skill_dir.is_dir():
        print(f"Error: {skill_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    from repo2skill.reviewer.g1 import run_g1_scan

    report = run_g1_scan(skill_dir)

    # Write report into verification/ directory (design.md §4)
    verification_dir = skill_dir / "verification"
    verification_dir.mkdir(parents=True, exist_ok=True)
    report_path = verification_dir / "g1_report.json"
    report_path.write_text(report.model_dump_json(indent=2, by_alias=True), encoding="utf-8")
    print(f"G1 report: {report_path}")

    if report.passed:
        print(f"G1 PASSED for {report.skill_name}")
    else:
        high = [f for f in report.findings if f["severity"] == "high"]
        medium = [f for f in report.findings if f["severity"] == "medium"]
        low = [f for f in report.findings if f["severity"] == "low"]
        print(f"G1 FAILED for {report.skill_name}: "
              f"{len(high)} HIGH, {len(medium)} MEDIUM, {len(low)} LOW")

    # Exit code: 0 if passed, 1 if failed
    sys.exit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
