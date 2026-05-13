"""Tests for Skill Suite detection and assembly."""

import tempfile
from pathlib import Path

from repo2skill.models import (
    AnalysisResult,
    Conditions,
    Interface,
    Policy,
    Skill,
    SkillCandidate,
    SuiteConfig,
    Termination,
)
from repo2skill.suite import (
    assemble_suite,
    detect_suite_mode,
    find_disconnected_clusters,
    infer_relations,
    validate_dag,
)


def make_candidate(
    id_: str,
    name: str = "",
    policy_type: str = "function",
    entry: str = "",
    steps: list[str] | None = None,
    dependencies: list[str] | None = None,
    allowed_tools: list[str] | None = None,
    description: str = "",
) -> SkillCandidate:
    return SkillCandidate(
        id=id_,
        name=name or f"Skill {id_}",
        description=description or f"Description for {id_}",
        policy=Policy(
            type=policy_type,
            entry=entry or f"{id_}.main",
            steps=steps or ["Step 1", "Step 2"],
            dependencies=dependencies or [],
        ),
        interface=Interface(allowed_tools=allowed_tools or ["Read"]),
    )


def make_skill(
    id_: str,
    name: str = "",
    policy_type: str = "function",
    entry: str = "",
    steps: list[str] | None = None,
    dependencies: list[str] | None = None,
    allowed_tools: list[str] | None = None,
    description: str = "",
) -> Skill:
    return Skill(
        id=id_,
        name=name or f"Skill {id_}",
        description=description or f"Description for {id_}",
        policy=Policy(
            type=policy_type,
            entry=entry or f"{id_}.main",
            steps=steps or ["Step 1", "Step 2"],
            dependencies=dependencies or [],
        ),
        interface=Interface(allowed_tools=allowed_tools or ["Read"]),
    )


class TestDetectSuiteMode:
    def test_single_candidate_returns_false(self):
        """One candidate should not trigger suite mode."""
        result = AnalysisResult(repo="test", skills=[])
        candidates = [make_candidate("sk1")]
        is_suite, reason = detect_suite_mode(result, candidates)
        assert is_suite is False

    def test_multiple_entry_points(self):
        """Candidates with different policy types should trigger suite mode."""
        result = AnalysisResult(repo="test", skills=[])
        candidates = [
            make_candidate("sk1", policy_type="script"),
            make_candidate("sk2", policy_type="function"),
        ]
        is_suite, reason = detect_suite_mode(result, candidates)
        assert is_suite is True
        assert "entry-point" in reason.lower()

    def test_divergent_allowed_tools(self):
        """Candidates with different tool sets should trigger suite mode."""
        result = AnalysisResult(repo="test", skills=[])
        candidates = [
            make_candidate("sk1", allowed_tools=["Read", "Write"]),
            make_candidate("sk2", allowed_tools=["Read", "Bash"]),
        ]
        is_suite, reason = detect_suite_mode(result, candidates)
        assert is_suite is True
        assert "tool" in reason.lower() or "divergent" in reason.lower()

    def test_large_combined_output(self):
        """Candidates with large combined output should trigger suite mode."""
        result = AnalysisResult(repo="test", skills=[])
        # Create candidates with very large descriptions/step lists to exceed token threshold
        long_text = "x" * 5000  # ~1250 tokens per candidate
        candidates = [
            make_candidate("sk1", description=long_text, steps=[long_text]),
            make_candidate("sk2", description=long_text, steps=[long_text]),
        ]
        is_suite, reason = detect_suite_mode(result, candidates)
        # Combined tokens should exceed 4000
        assert is_suite is True


class TestDisconnectedClusters:
    def test_connected_graph(self):
        """A fully connected graph has one cluster."""
        dep_graph = {
            "nodes": ["a", "b", "c"],
            "edges": [
                {"source": "a", "target": "b", "type": "internal"},
                {"source": "b", "target": "c", "type": "internal"},
            ],
        }
        clusters = find_disconnected_clusters(dep_graph)
        assert len(clusters) == 1
        assert len(clusters[0]) == 3

    def test_disconnected_graph(self):
        """A graph with two components returns two clusters."""
        dep_graph = {
            "nodes": ["a", "b", "c", "d"],
            "edges": [
                {"source": "a", "target": "b", "type": "internal"},
                {"source": "c", "target": "d", "type": "internal"},
            ],
        }
        clusters = find_disconnected_clusters(dep_graph)
        assert len(clusters) == 2

    def test_empty_graph(self):
        """Empty graph returns no clusters."""
        clusters = find_disconnected_clusters({})
        assert clusters == []

    def test_no_edges(self):
        """Nodes with no edges each form their own cluster."""
        dep_graph = {"nodes": ["a", "b", "c"], "edges": []}
        clusters = find_disconnected_clusters(dep_graph)
        assert len(clusters) == 3  # each node isolated


class TestInferRelations:
    def test_depends_on_from_graph(self):
        """Dependency edges should translate to depends-on relations."""
        candidates = [
            make_skill("sk1", entry="module_a.main"),
            make_skill("sk2", entry="module_b.run"),
        ]
        dep_graph = {
            "nodes": ["module_a", "module_b"],
            "edges": [
                {"source": "module_a", "target": "module_b", "type": "internal"},
            ],
        }
        relations = infer_relations(candidates, dep_graph)
        depends = [r for r in relations if r["type"] == "depends-on"]
        assert len(depends) == 1
        assert depends[0]["source"] == "sk1"
        assert depends[0]["target"] == "sk2"

    def test_bundled_with(self):
        """Same policy type and tools → bundled-with."""
        candidates = [
            make_skill("sk1", policy_type="script", allowed_tools=["Read", "Write"]),
            make_skill("sk2", policy_type="script", allowed_tools=["Read", "Write"]),
        ]
        relations = infer_relations(candidates, {})
        bundled = [r for r in relations if r["type"] == "bundled-with"]
        assert len(bundled) == 1

    def test_no_self_relations(self):
        """A skill should not have relations to itself."""
        candidates = [
            make_skill("sk1", entry="module_a.main"),
        ]
        dep_graph = {
            "nodes": ["module_a"],
            "edges": [],
        }
        relations = infer_relations(candidates, dep_graph)
        for r in relations:
            assert r["source"] != r["target"]


class TestValidateDAG:
    def test_valid_dag(self):
        relations = [
            {"source": "sk1", "target": "sk2", "type": "depends-on"},
            {"source": "sk2", "target": "sk3", "type": "depends-on"},
        ]
        valid, msg = validate_dag(relations)
        assert valid is True

    def test_cycle_detected(self):
        relations = [
            {"source": "sk1", "target": "sk2", "type": "depends-on"},
            {"source": "sk2", "target": "sk1", "type": "depends-on"},
        ]
        valid, msg = validate_dag(relations)
        assert valid is False
        assert "cycle" in msg.lower()

    def test_non_dep_relations_ignored(self):
        """composes and bundled-with should not be checked for cycles."""
        relations = [
            {"source": "sk1", "target": "sk2", "type": "composes"},
            {"source": "sk2", "target": "sk1", "type": "bundled-with"},
        ]
        valid, _ = validate_dag(relations)
        assert valid is True  # only checks depends-on and requires-output-from


class TestAssembleSuite:
    def test_assemble_suite_creates_output(self):
        """Assemble suite should create suite.yaml and per-skill directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "output"
            out.mkdir()

            candidates = [
                make_skill("sk1", name="Web Server"),
                make_skill("sk2", name="Database Layer"),
            ]
            config = SuiteConfig(
                name="Test App",
                description="A test application suite",
                skills=["sk1", "sk2"],
                relations=[
                    {"source": "sk1", "target": "sk2", "type": "depends-on"},
                ],
            )

            suite_dir = assemble_suite(config, candidates, out, source="/test/repo")

            assert suite_dir.exists()
            assert (suite_dir / "suite.yaml").exists()
            # Each skill should have its own subdirectory
            assert (suite_dir / "web-server-skill").exists()
            assert (suite_dir / "database-layer-skill").exists()
            assert (suite_dir / "web-server-skill" / "SKILL.md").exists()
            assert (suite_dir / "database-layer-skill" / "SKILL.md").exists()

    def test_assemble_suite_with_candidate_input(self):
        """Assemble suite should handle SkillCandidate input by converting to Skill."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "output"
            out.mkdir()

            candidates = [
                make_candidate("sk1", name="Formatter"),
            ]
            config = SuiteConfig(
                name="Test Suite",
                description="Test",
                skills=["sk1"],
                relations=[],
            )

            suite_dir = assemble_suite(config, candidates, out)
            assert suite_dir.exists()
            assert (suite_dir / "suite.yaml").exists()
            assert (suite_dir / "formatter-skill").exists()
