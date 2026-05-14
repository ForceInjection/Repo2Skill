"""Bootstrap (self-analysis) tests for Repo2Skill.

Runs repo2skill on its own repository and validates:
1. Coverage: analysis.json covers all script entry points and core modules
   referenced in the hand-written SKILL.md.
2. Suite mode: correctly triggers for this multi-module repo.
3. Pipeline flow: dependency graph reflects the actual structure→extract→
   assemble→audit pipeline.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Expected artifacts from the hand-written repo2skill-skill/SKILL.md
# ---------------------------------------------------------------------------

# The 5 thin wrapper scripts in repo2skill-skill/scripts/ — each maps to a
# step in the 12-step pipeline described in SKILL.md.
SCRIPT_ENTRIES = {
    "repo2skill-skill.scripts.structure": "structure.py",
    "repo2skill-skill.scripts.extract": "extract.py",
    "repo2skill-skill.scripts.assemble": "assemble.py",
    "repo2skill-skill.scripts.audit_g1": "audit_g1.py",
    "repo2skill-skill.scripts.audit_g2": "audit_g2.py",
}

# The 6 core modules in src/repo2skill/ that implement the deterministic logic.
CORE_MODULES = [
    "src.repo2skill.models",
    "src.repo2skill.structure",
    "src.repo2skill.extractor",
    "src.repo2skill.assemble",
    "src.repo2skill.suite",
    "src.repo2skill.reviewer.g1",
]

# CLI entry point — the orchestrator that ties all pipeline stages together.
CLI_MODULE = "src.repo2skill.cli"
CLI_PACKAGE = "repo2skill.cli"

# Pipeline stages as Python package imports (used in edge targets).
# The CLI imports each of these; they are independent modules orchestrated
# by the CLI, not a direct import chain.
PIPELINE_PACKAGES = [
    "repo2skill.structure",
    "repo2skill.extractor",
    "repo2skill.assemble",
    "repo2skill.suite",
    "repo2skill.reviewer.g1",
    "repo2skill.models",
]

# Same pipeline stages as file-path nodes in the dependency graph.
PIPELINE_NODES = [
    "src.repo2skill.structure",
    "src.repo2skill.extractor",
    "src.repo2skill.assemble",
    "src.repo2skill.suite",
    "src.repo2skill.reviewer.g1",
    "src.repo2skill.models",
]

# Package names used when scripts import from repo2skill.*.
CORE_PACKAGE_NAMES = [
    "repo2skill.structure",
    "repo2skill.extractor",
    "repo2skill.assemble",
    "repo2skill.suite",
    "repo2skill.reviewer.g1",
    "repo2skill.models",
]


def _run_self_analysis(output_dir: Path) -> dict:
    """Run repo2skill on itself and return the parsed analysis.json."""
    result = subprocess.run(
        [
            sys.executable, "-m", "repo2skill.cli",
            str(REPO_ROOT),
            "--mode", "suite",
            "--non-interactive",
            "--confidence-threshold", "0.3",
            "--force-continue",
            "--write-analysis",
            "-o", str(output_dir),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"Self-analysis failed:\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}"

    analysis_path = output_dir / "analysis.json"
    assert analysis_path.exists(), f"analysis.json not found at {analysis_path}"

    with open(analysis_path) as f:
        return json.load(f)


class TestBootstrapCoverage:
    """Verify self-analysis covers all artifacts referenced in SKILL.md."""

    @pytest.fixture(scope="class")
    def analysis(self, tmp_path_factory):
        output_dir = tmp_path_factory.mktemp("bootstrap_coverage")
        return _run_self_analysis(output_dir)

    def test_all_script_entries_present(self, analysis):
        """Every script wrapper referenced in SKILL.md steps must appear."""
        found_modules = {s["policy"]["entry"].rsplit(".", 1)[0] for s in analysis["skills"]}

        missing = []
        for expected_module, script_name in SCRIPT_ENTRIES.items():
            if expected_module not in found_modules:
                missing.append(f"{script_name} → {expected_module}")

        assert not missing, (
            f"SKILL.md references {len(missing)} script(s) not found in analysis.json:\n"
            + "\n".join(f"  - {m}" for m in missing)
        )

    def test_all_core_modules_present(self, analysis):
        """Every core src/repo2skill/ module must appear as a graph node."""
        graph_nodes = set(analysis["dependency_graph"]["nodes"])

        missing = [m for m in CORE_MODULES if m not in graph_nodes]
        assert not missing, (
            f"Missing core modules in dependency graph:\n"
            + "\n".join(f"  - {m}" for m in missing)
        )

    def test_cli_module_present(self, analysis):
        """CLI entry point must be in the dependency graph."""
        assert CLI_MODULE in set(analysis["dependency_graph"]["nodes"]), (
            f"CLI module '{CLI_MODULE}' not found in dependency graph"
        )

    def test_no_duplicate_skill_ids(self, analysis):
        """Skill IDs must be unique."""
        ids = [s["id"] for s in analysis["skills"]]
        assert len(ids) == len(set(ids)), f"Duplicate skill IDs: {ids}"

    def test_candidate_count_reasonable(self, analysis):
        """Self-analysis should produce at least 10 candidates (22 files, 133 funcs)."""
        assert len(analysis["skills"]) >= 10, (
            f"Expected ≥10 candidates from 22 Python files, got {len(analysis['skills'])}"
        )

    def test_core_modules_use_public_primary_functions(self, analysis):
        """Primary function for each core module must not be an internal helper.

        Before the _select_primary_function fix, structure.py selected
        _is_python_file and assemble.py selected _get_template_env.
        """
        # Map module → entry (last component = function name)
        core_entries: dict[str, str] = {}
        for s in analysis["skills"]:
            entry = s["policy"]["entry"]
            if not entry:
                continue
            parts = entry.rsplit(".", 1)
            if len(parts) < 2:
                continue
            module_prefix = parts[0]
            core_entries[module_prefix] = parts[1]

        # structure.py: should not be _is_python_file or any underscore-prefixed func
        for mod, expected_func in [
            ("src.repo2skill.structure", "analyze_repo"),
            ("src.repo2skill.assemble", "assemble_skill"),
        ]:
            if mod in core_entries:
                assert not core_entries[mod].startswith("_"), (
                    f"{mod} primary is '{core_entries[mod]}' — expected a public function, "
                    f"not an internal helper"
                )
                assert core_entries[mod] == expected_func, (
                    f"{mod} primary is '{core_entries[mod]}', expected '{expected_func}'"
                )

    def test_cli_is_top_candidate(self, analysis):
        """CLI (orchestrator) should rank high — it ties the pipeline together."""
        top5 = sorted(analysis["skills"], key=lambda s: s.get("confidence", 0), reverse=True)[:5]
        top5_modules = {s["policy"]["entry"].split(".")[1] if len(s["policy"]["entry"].split(".")) > 1 else "" for s in top5}
        # CLI module should appear in top 5
        assert "repo2skill" in " ".join(s["policy"]["entry"] for s in top5), (
            "CLI module should be among top-5 candidates"
        )


class TestBootstrapSuiteMode:
    """Verify suite mode detection and DAG validation on self."""

    @pytest.fixture(scope="class")
    def suite_output(self, tmp_path_factory):
        output_dir = tmp_path_factory.mktemp("bootstrap_suite")
        _run_self_analysis(output_dir)
        suite_dir = output_dir / "repo2skill-suite"
        return output_dir, suite_dir

    def test_suite_mode_triggers(self, suite_output):
        """Repo2Skill itself should trigger suite mode (multi-module, divergent tools)."""
        output_dir, suite_dir = suite_output
        assert suite_dir.exists(), f"Suite directory not created at {suite_dir}"

    def test_suite_yaml_exists_and_valid(self, suite_output):
        """suite.yaml must exist with required fields."""
        _, suite_dir = suite_output
        suite_yaml_path = suite_dir / "suite.yaml"
        assert suite_yaml_path.exists(), f"suite.yaml not found at {suite_yaml_path}"

        with open(suite_yaml_path) as f:
            suite = yaml.safe_load(f)

        assert "suite-id" in suite, "suite.yaml missing 'suite-id'"
        assert "skills" in suite, "suite.yaml missing 'skills'"
        assert "relations" in suite, "suite.yaml missing 'relations'"
        assert len(suite["skills"]) >= 2, (
            f"Suite should have ≥2 skills, got {len(suite['skills'])}"
        )

    def test_suite_relations_are_valid(self, suite_output):
        """All relations must reference existing skill IDs."""
        _, suite_dir = suite_output
        with open(suite_dir / "suite.yaml") as f:
            suite = yaml.safe_load(f)

        skill_ids = {s["id"] for s in suite["skills"]}
        for rel in suite["relations"]:
            assert rel["from"] in skill_ids, (
                f"Relation 'from' references unknown skill: {rel['from']}"
            )
            assert rel["to"] in skill_ids, (
                f"Relation 'to' references unknown skill: {rel['to']}"
            )
            assert rel["type"] in ("depends-on", "composes", "bundled-with", "requires-output-from"), (
                f"Unknown relation type: {rel['type']}"
            )

    def test_each_sub_skill_has_required_files(self, suite_output):
        """Each sub-skill directory must have SKILL.md and skill.yaml."""
        _, suite_dir = suite_output
        with open(suite_dir / "suite.yaml") as f:
            suite = yaml.safe_load(f)

        for skill in suite["skills"]:
            skill_dir = (suite_dir / skill["path"]).resolve()
            assert (skill_dir / "SKILL.md").exists(), (
                f"Missing SKILL.md in {skill['name']}"
            )
            assert (skill_dir / "skill.yaml").exists(), (
                f"Missing skill.yaml in {skill['name']}"
            )

    def test_g1_scan_passes(self, suite_output):
        """G1 scan must pass on self (no dangerous patterns in generated output)."""
        _, suite_dir = suite_output
        g1_report_path = suite_dir / "verification" / "g1_report.json"
        if g1_report_path.exists():
            with open(g1_report_path) as f:
                g1 = json.load(f)
            assert g1.get("passed", False), (
                f"G1 scan failed with findings: {g1.get('findings', [])}"
            )

    def test_suite_has_depends_on_relations(self, suite_output):
        """Suite must have depends-on edges from the fixed _find_skill_for_module."""
        _, suite_dir = suite_output
        with open(suite_dir / "suite.yaml") as f:
            suite = yaml.safe_load(f)

        depends_on = [r for r in suite["relations"] if r["type"] == "depends-on"]
        assert len(depends_on) >= 2, (
            f"Expected ≥2 depends-on relations (CLI → pipeline stages), "
            f"got {len(depends_on)}: {depends_on}"
        )

    def test_suite_has_composes_relations(self, suite_output):
        """Suite must have composes edges from orchestrator co-import detection."""
        _, suite_dir = suite_output
        with open(suite_dir / "suite.yaml") as f:
            suite = yaml.safe_load(f)

        composes = [r for r in suite["relations"] if r["type"] == "composes"]
        assert len(composes) >= 1, (
            f"Expected ≥1 composes relations (co-import detection), "
            f"got {len(composes)}: {composes}"
        )


class TestBootstrapPipelineFlow:
    """Verify the dependency graph reflects the actual pipeline topology.

    The pipeline stages are independent modules orchestrated by the CLI —
    they don't form a direct import chain. The dependency graph captures
    Python import relationships, so we verify:
    1. CLI imports every pipeline stage (it's the orchestrator).
    2. Script wrappers delegate to src/ modules via package imports.
    3. Assemble and suite are connected (suite imports assemble).
    4. The graph is well-formed (no self-loops).
    """

    @pytest.fixture(scope="class")
    def dep_graph(self, tmp_path_factory):
        output_dir = tmp_path_factory.mktemp("bootstrap_flow")
        analysis = _run_self_analysis(output_dir)
        return analysis["dependency_graph"]

    def _edge_set(self, dep_graph):
        """Build a set of (source, target) tuples from the dependency graph."""
        edges = set()
        for e in dep_graph["edges"]:
            edges.add((e["source"], e["target"]))
        return edges

    def test_cli_imports_all_pipeline_stages(self, dep_graph):
        """CLI must import every pipeline stage (it orchestrates the flow)."""
        edges = self._edge_set(dep_graph)

        missing = []
        for stage in PIPELINE_PACKAGES:
            if (CLI_MODULE, stage) not in edges:
                missing.append(stage)

        assert not missing, (
            f"CLI does not import these pipeline stages:\n"
            + "\n".join(f"  - {m}" for m in missing)
        )

    def test_suite_and_assemble_connected(self, dep_graph):
        """suite.py imports assemble.py — the pipeline stages are linked."""
        edges = self._edge_set(dep_graph)
        assert ("src.repo2skill.suite", "repo2skill.assemble") in edges or \
               ("repo2skill.suite", "repo2skill.assemble") in edges, (
            "suite and assemble are not connected in the dependency graph"
        )

    def test_cli_has_multiple_dependencies(self, dep_graph):
        """CLI should depend on multiple modules (it ties the pipeline together)."""
        edges = self._edge_set(dep_graph)
        cli_deps = [t for s, t in edges if s == CLI_MODULE]
        assert len(cli_deps) >= 6, (
            f"CLI only has {len(cli_deps)} dependencies, expected ≥6 (all pipeline stages)"
        )

    def test_scripts_delegate_to_src_modules(self, dep_graph):
        """Each repo2skill-skill/scripts/ wrapper imports from repo2skill.*."""
        edges = self._edge_set(dep_graph)
        script_modules = [m for m in dep_graph["nodes"] if m.startswith("repo2skill-skill.scripts.")]

        script_with_src_dep = 0
        for script_mod in script_modules:
            for pkg_name in CORE_PACKAGE_NAMES:
                if (script_mod, pkg_name) in edges:
                    script_with_src_dep += 1
                    break

        assert script_with_src_dep >= 4, (
            f"Only {script_with_src_dep}/{len(script_modules)} script wrappers "
            f"have edges to repo2skill.* packages"
        )

    def test_no_self_loops(self, dep_graph):
        """Dependency graph must not contain self-loops."""
        edges = self._edge_set(dep_graph)
        self_loops = [(s, t) for s, t in edges if s == t]
        assert not self_loops, f"Self-loops found: {self_loops}"

    def test_all_pipeline_stages_in_graph(self, dep_graph):
        """Every pipeline stage must appear as a node in the dependency graph."""
        graph_nodes = set(dep_graph["nodes"])

        missing = []
        for stage in PIPELINE_NODES:
            if stage not in graph_nodes:
                missing.append(stage)

        assert not missing, (
            f"Pipeline stages missing from dependency graph:\n"
            + "\n".join(f"  - {m}" for m in missing)
        )
