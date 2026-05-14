"""CLI entry point for Repo2Skill.

Orchestrates the deterministic pipeline: structure → extract → suite detection
→ assemble → G1 scan → trust level. The Agent (Claude Code) handles LLM-driven
extraction refinement and G2 semantic review by following SKILL.md instructions.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import typer

from repo2skill.assemble import assemble_skill
from repo2skill.extractor import extract_skills_with_scores
from repo2skill.models import Skill, SkillCandidate, SuiteConfig
from repo2skill.reviewer.g1 import run_g1_scan
from repo2skill.structure import analyze_repo
from repo2skill.suite import (
    assemble_suite,
    compute_suite_trust_level,
    detect_suite_mode,
    infer_relations,
    validate_dag,
)

app = typer.Typer(
    name="repo2skill",
    help="Decompose a Git repository into a standards-compliant Agent Skill.",
)

logger = logging.getLogger(__name__)


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )


@app.command()
def main(
    source: str = typer.Argument(
        ...,
        help="GitHub URL, git URL, or local path to a Python repository",
    ),
    out: Path = typer.Option(
        Path.cwd(),
        "--out",
        "-o",
        help="Output directory for the generated skill",
        file_okay=False,
        dir_okay=True,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
    interactive: bool = typer.Option(
        True,
        "--interactive/--non-interactive",
        help="Enable interactive candidate selection (default: interactive)",
    ),
    mode: str = typer.Option(
        "auto",
        "--mode",
        help="Output mode: single, suite, or auto (detect from repo structure)",
    ),
    confidence_threshold: float = typer.Option(
        0.5,
        "--confidence-threshold",
        help="Minimum confidence for auto-selection in non-interactive mode",
    ),
    force_continue: bool = typer.Option(
        False,
        "--force-continue",
        help="Continue even if G1 scan finds high-severity issues",
    ),
    write_analysis: bool = typer.Option(
        False,
        "--write-analysis",
        help="Write analysis.json to output directory for Agent consumption",
    ),
    skip_g3: bool = typer.Option(
        False,
        "--skip-g3",
        help="Skip G3 sandbox verification (placeholder, G3 not yet implemented)",
    ),
) -> None:
    """Convert a Python repository into an Agent Skill.

    Runs the deterministic pipeline. For LLM-driven extraction refinement
    and G2 semantic review, the Agent reads the outputs and applies reasoning
    following SKILL.md instructions.
    """
    _setup_logging(verbose)
    if skip_g3:
        typer.echo("Note: --skip-g3 is a placeholder — G3 sandbox is Phase 3 scope.")

    # =========================================================================
    # Step 1: Structure — analyze the repo
    # =========================================================================
    typer.echo(f"Analyzing: {source}")
    result = analyze_repo(source)

    if not result.skills:
        typer.echo("No Python functions found in the repository.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Found {len(result.skills)} candidate skill(s)")

    # Write analysis.json for Agent consumption
    if write_analysis:
        analysis_path = out / "analysis.json"
        analysis_path.parent.mkdir(parents=True, exist_ok=True)
        analysis_path.write_text(result.model_dump_json(indent=2, by_alias=True), encoding="utf-8")
        typer.echo(f"Wrote analysis.json to {analysis_path}")

    # =========================================================================
    # Step 2: Extract — score and rank candidates (rule-based baseline)
    # =========================================================================
    candidates = extract_skills_with_scores(result)

    if not candidates:
        typer.echo("No suitable candidates identified.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"\nTop {len(candidates)} candidate(s):")
    for c in candidates:
        typer.echo(
            f"  [{c.id}] {c.name} (confidence: {c.confidence:.2f})"
        )

    # =========================================================================
    # Step 3: Mode selection — single vs suite
    # =========================================================================
    is_suite, suite_reason = detect_suite_mode(result, candidates)

    use_suite = mode == "suite" or (mode == "auto" and is_suite)
    if mode == "single":
        use_suite = False

    if use_suite:
        typer.echo(f"\nSuite mode: {suite_reason}")
    elif is_suite and mode == "auto":
        typer.echo(f"\nSuite criteria met ({suite_reason}), but using single mode")

    # =========================================================================
    # Step 4: Candidate selection
    # =========================================================================
    selected: list[Skill] = []

    if interactive:
        selected = _interactive_selection(candidates)
    else:
        # Non-interactive: auto-select candidates above confidence threshold
        for c in candidates:
            if c.confidence >= confidence_threshold:
                selected.append(c)
        if not selected:
            # Fallback: take the top candidate
            selected = [candidates[0]]
            typer.echo(
                f"\nNo candidates above threshold {confidence_threshold}, "
                f"falling back to top candidate: {selected[0].name}"
            )

    if not selected:
        typer.echo("No candidates selected.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"\nSelected {len(selected)} skill(s):")
    for s in selected:
        typer.echo(f"  - {s.name} ({s.id})")

    # =========================================================================
    # Step 5: Assemble — render templates and write output (L0 baseline)
    # =========================================================================
    if use_suite and len(selected) > 1:
        suite_dir = _assemble_as_suite(selected, result, out, source, trust_level="L0")
        skill_dirs = [suite_dir]
    else:
        skill_dirs = []
        for s in selected:
            skill_dir = assemble_skill(
                s, out, source=source, trust_level="L0", g1_passed=False
            )
            skill_dirs.append(skill_dir)

    # =========================================================================
    # Step 6: G1 static security scan
    # =========================================================================
    typer.echo("\nRunning G1 static security scan...")
    all_g1_passed = True
    g1_reports: dict[Path, object] = {}
    for skill_dir in skill_dirs:
        if skill_dir.exists():
            g1_report = run_g1_scan(skill_dir)
            g1_reports[skill_dir] = g1_report
            _print_g1_report(g1_report)
            # Persist G1 report into verification/ (design.md §4)
            _write_g1_report(skill_dir, g1_report)
            if not g1_report.passed:
                all_g1_passed = False

    if not all_g1_passed and not force_continue:
        typer.echo(
            "\nG1 scan found high-severity issues. Use --force-continue to override.",
            err=True,
        )
        typer.echo(
            "Review the findings above and ensure no malicious code is included."
        )
        raise typer.Exit(code=1)

    # =========================================================================
    # Step 7: Compute trust level and update assembled skill.yaml
    # =========================================================================
    trust_level = "L1" if all_g1_passed else "L0"

    if use_suite and len(selected) > 1:
        # Suite mode: per-member trust + relation completeness penalty
        member_levels = _compute_member_trust_levels(selected, all_g1_passed)
        suite_level, reason = compute_suite_trust_level(
            member_levels, _get_suite_relations(skill_dirs)
        )
        trust_level = suite_level
        typer.echo(f"\nSuite trust level: {trust_level} ({reason})")
        _update_suite_yaml_trust(skill_dirs, suite_level, member_levels)
    else:
        typer.echo(f"\nInitial trust level: {trust_level}")
        _update_skill_yaml_trust(skill_dirs, trust_level, all_g1_passed)

    typer.echo(
        "For G2 semantic review, have the Agent (Claude Code) follow"
        " the G2 instructions in SKILL.md."
    )

    # =========================================================================
    # Summary
    # =========================================================================
    typer.echo(f"\n--- Done ---")
    for skill_dir in skill_dirs:
        if skill_dir.exists():
            typer.echo(f"Skill at: {skill_dir}")
            typer.echo(f"  SKILL.md:  {skill_dir / 'SKILL.md'}")
            typer.echo(f"  skill.yaml: {skill_dir / 'skill.yaml'}")
            if (skill_dir / "suite.yaml").exists():
                typer.echo(f"  suite.yaml: {skill_dir / 'suite.yaml'}")


def _interactive_selection(
    candidates: list[SkillCandidate],
) -> list[Skill]:
    """Present candidates to user for interactive selection."""
    typer.echo(
        "\nSelect skills to generate (enter IDs separated by commas, 'all', or 'none'):"
    )
    for c in candidates:
        typer.echo(
            f"  [{c.id}] {c.name}\n"
            f"      confidence: {c.confidence:.2f} | "
            f"reasoning: {c.reasoning}"
        )

    choice = typer.prompt(
        "Selection",
        default="all",
        show_default=True,
    )

    choice = choice.strip().lower()
    if choice == "all":
        return [
            Skill(**c.model_dump(exclude={"confidence", "reasoning", "scores"}))
            for c in candidates
        ]
    if choice == "none":
        typer.echo("Selection cancelled.")
        raise typer.Exit(code=0)

    selected = []
    valid_ids = {c.id for c in candidates}
    selected_ids = [s.strip() for s in choice.split(",")]
    for sid in selected_ids:
        if sid in valid_ids:
            c = next(c for c in candidates if c.id == sid)
            selected.append(
                Skill(**c.model_dump(exclude={"confidence", "reasoning", "scores"}))
            )
        else:
            typer.echo(f"Warning: '{sid}' is not a valid candidate ID, skipping.", err=True)

    if not selected:
        typer.echo("No valid candidates selected, using all.", err=True)
        return [
            Skill(**c.model_dump(exclude={"confidence", "reasoning", "scores"}))
            for c in candidates
        ]
    return selected


def _assemble_as_suite(
    selected: list[Skill],
    result,  # AnalysisResult
    out: Path,
    source: str,
    trust_level: str = "L0",
) -> Path:
    """Assemble selected skills as a Skill Suite."""
    relations = infer_relations(selected, result.dependency_graph)
    valid, dag_msg = validate_dag(relations)
    if not valid:
        typer.echo(f"Warning: {dag_msg}", err=True)

    suite_config = SuiteConfig(
        name=result.repo,
        description=f"Skill suite for {result.repo}",
        skills=[s.id for s in selected],
        relations=relations,
    )

    suite_dir = assemble_suite(
        suite_config, selected, out, source=source, trust_level=trust_level,
    )
    typer.echo(f"Assembled skill suite at: {suite_dir}")
    return suite_dir


def _print_g1_report(report) -> None:
    """Print a G1 scan report summary."""
    if report.passed:
        typer.echo(f"  {report.skill_name}: PASSED")
    else:
        typer.echo(f"  {report.skill_name}: FAILED ({len(report.findings)} finding(s))")
        high = [f for f in report.findings if f["severity"] == "high"]
        medium = [f for f in report.findings if f["severity"] == "medium"]
        low = [f for f in report.findings if f["severity"] == "low"]
        if high:
            typer.echo(f"    HIGH: {len(high)}")
            for f in high:
                typer.echo(f"      {f['file']}:{f['line']} — {f['description']}")
        if medium:
            typer.echo(f"    MEDIUM: {len(medium)}")
        if low:
            typer.echo(f"    LOW: {len(low)}")


def _write_g1_report(skill_dir: Path, report) -> None:
    """Persist G1 report into verification/ (design.md §4)."""
    verification_dir = skill_dir / "verification"
    verification_dir.mkdir(parents=True, exist_ok=True)
    report_path = verification_dir / "g1_report.json"
    report_path.write_text(report.model_dump_json(indent=2, by_alias=True), encoding="utf-8")


def _update_skill_yaml_trust(
    skill_dirs: list[Path], trust_level: str, g1_passed: bool
) -> None:
    """Update skill.yaml files with computed trust level and G1 status."""
    import yaml

    for skill_dir in skill_dirs:
        # Update sub-skill skill.yaml files if this is a suite directory
        for yaml_path in skill_dir.rglob("skill.yaml"):
            try:
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
                data["trust-level"] = trust_level
                if "security" in data and isinstance(data["security"], dict):
                    data["security"]["g1-passed"] = g1_passed
                yaml_path.write_text(
                    yaml.dump(data, default_flow_style=False, allow_unicode=True),
                    encoding="utf-8",
                )
            except Exception:
                pass  # Non-critical; trust level is reported to user regardless


def _compute_member_trust_levels(
    selected: list, all_g1_passed: bool
) -> dict[str, str]:
    """Compute per-skill trust level from suite-level G1 result.

    For suite mode, G1 scans the entire suite directory and produces a single
    report. All members inherit the same G1 result until per-skill G1 is
    implemented (Phase 3).
    """
    base = "L1" if all_g1_passed else "L0"
    member_levels: dict[str, str] = {}
    for s in selected:
        sid = s.id if hasattr(s, "id") else s.get("id", "")
        member_levels[sid] = base
    return member_levels


def _get_suite_relations(skill_dirs: list[Path]) -> list[dict]:
    """Read suite.yaml relations from the first suite directory found."""
    import yaml

    for skill_dir in skill_dirs:
        suite_yaml = skill_dir / "suite.yaml"
        if suite_yaml.exists():
            data = yaml.safe_load(suite_yaml.read_text(encoding="utf-8")) or {}
            return data.get("relations", [])
    return []


def _update_suite_yaml_trust(
    skill_dirs: list[Path],
    suite_level: str,
    member_levels: dict[str, str],
) -> None:
    """Update suite.yaml and sub-skill skill.yaml files with computed trust levels."""
    import yaml

    for skill_dir in skill_dirs:
        # Update suite.yaml
        suite_yaml = skill_dir / "suite.yaml"
        if suite_yaml.exists():
            data = yaml.safe_load(suite_yaml.read_text(encoding="utf-8")) or {}
            data["trust-level"] = suite_level
            suite_yaml.write_text(
                yaml.dump(data, default_flow_style=False, allow_unicode=True),
                encoding="utf-8",
            )

        # Update per-sub-skill skill.yaml files
        for yaml_path in skill_dir.rglob("skill.yaml"):
            try:
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
                # Match yaml path to a member by scanning for skill ID in path
                matched_level = None
                for sid, level in member_levels.items():
                    if sid in str(yaml_path.parent):
                        matched_level = level
                        break
                if matched_level is None:
                    matched_level = suite_level
                data["trust-level"] = matched_level
                if "security" in data and isinstance(data["security"], dict):
                    data["security"]["g1-passed"] = matched_level != "L0"
                yaml_path.write_text(
                    yaml.dump(data, default_flow_style=False, allow_unicode=True),
                    encoding="utf-8",
                )
            except Exception:
                pass


if __name__ == "__main__":
    app()
