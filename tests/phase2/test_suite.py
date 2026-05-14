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
    compute_suite_trust_level,
    detect_skill_overlap,
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


class TestComputeSuiteTrustLevel:
    """Tests for suite-level trust level computation (P4-T8)."""

    def test_all_l1_no_penalty(self):
        """All members L1 + complete directional edges → L1."""
        member_levels = {"sk1": "L1", "sk2": "L1", "sk3": "L1"}
        relations = [
            {"source": "sk1", "target": "sk2", "type": "depends-on"},
            {"source": "sk2", "target": "sk3", "type": "depends-on"},
        ]
        level, reason = compute_suite_trust_level(member_levels, relations)
        assert level == "L1"
        assert "downgraded" not in reason

    def test_all_l1_incomplete_relations(self):
        """All L1 but missing directional edges → downgrade to L0."""
        member_levels = {"sk1": "L1", "sk2": "L1", "sk3": "L1"}
        relations = []  # No depends-on edges
        level, reason = compute_suite_trust_level(member_levels, relations)
        assert level == "L0"
        assert "downgraded" in reason

    def test_mixed_levels_min_wins(self):
        """Mixed L0/L1/L2 → min (L0) wins, no further downgrade."""
        member_levels = {"sk1": "L2", "sk2": "L1", "sk3": "L0"}
        relations = [
            {"source": "sk1", "target": "sk2", "type": "depends-on"},
            {"source": "sk2", "target": "sk3", "type": "depends-on"},
        ]
        level, _ = compute_suite_trust_level(member_levels, relations)
        assert level == "L0"

    def test_single_member(self):
        """Single member — no relation penalty possible."""
        member_levels = {"sk1": "L2"}
        level, _ = compute_suite_trust_level(member_levels, [])
        assert level == "L2"

    def test_empty_members(self):
        """No members → L0."""
        level, reason = compute_suite_trust_level({}, [])
        assert level == "L0"
        assert "No member" in reason

    def test_composes_not_counted_as_directional(self):
        """composes and bundled-with don't satisfy the directional edge requirement."""
        member_levels = {"sk1": "L1", "sk2": "L1", "sk3": "L1"}
        relations = [
            {"source": "sk1", "target": "sk2", "type": "composes"},
            {"source": "sk2", "target": "sk3", "type": "bundled-with"},
        ]
        level, reason = compute_suite_trust_level(member_levels, relations)
        # 3 skills need ≥2 directional edges, but composes/bundled-with are not directional
        assert level == "L0"
        assert "downgraded" in reason

    def test_requires_output_from_counts_as_directional(self):
        """requires-output-from is a directional edge."""
        member_levels = {"sk1": "L1", "sk2": "L1", "sk3": "L1"}
        relations = [
            {"source": "sk1", "target": "sk2", "type": "requires-output-from"},
            {"source": "sk2", "target": "sk3", "type": "requires-output-from"},
        ]
        level, reason = compute_suite_trust_level(member_levels, relations)
        assert level == "L1"
        assert "downgraded" not in reason

    def test_boundary_two_skills_one_edge(self):
        """2 skills + 1 depends-on → just enough, no penalty."""
        member_levels = {"sk1": "L1", "sk2": "L1"}
        relations = [{"source": "sk1", "target": "sk2", "type": "depends-on"}]
        level, _ = compute_suite_trust_level(member_levels, relations)
        assert level == "L1"


class TestRequiresOutputFromChains:
    """Integration tests for requires-output-from pipeline chains (P4-T7).

    Verifies that skills connected by requires-output-from can be validated
    as a DAG (cycle detection), assembled into a suite, and topologically
    ordered to form an executable pipeline.
    """

    def test_requires_output_from_cycle_detected(self):
        """A requires-output-from cycle must be caught by validate_dag."""
        relations = [
            {"source": "sk1", "target": "sk2", "type": "requires-output-from"},
            {"source": "sk2", "target": "sk1", "type": "requires-output-from"},
        ]
        valid, msg = validate_dag(relations)
        assert valid is False
        assert "cycle" in msg.lower()

    def test_requires_output_from_chain_is_valid(self):
        """A linear requires-output-from chain must be a valid DAG."""
        relations = [
            {"source": "sk1", "target": "sk2", "type": "requires-output-from"},
            {"source": "sk2", "target": "sk3", "type": "requires-output-from"},
            {"source": "sk3", "target": "sk4", "type": "requires-output-from"},
        ]
        valid, msg = validate_dag(relations)
        assert valid is True

    def test_assemble_suite_with_requires_output_from(self):
        """Suite assembles correctly with requires-output-from relations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "output"
            out.mkdir()

            candidates = [
                make_skill("sk1", name="Data Fetcher",
                           description="Fetch raw data from source",
                           allowed_tools=["Bash", "Read"]),
                make_skill("sk2", name="Data Cleaner",
                           description="Clean and normalize fetched data",
                           allowed_tools=["Read", "Write"]),
                make_skill("sk3", name="Data Reporter",
                           description="Generate report from cleaned data",
                           allowed_tools=["Read", "Write"]),
            ]
            config = SuiteConfig(
                name="Data Pipeline",
                description="A three-stage data processing pipeline",
                skills=["sk1", "sk2", "sk3"],
                relations=[
                    {"source": "sk2", "target": "sk1", "type": "requires-output-from"},
                    {"source": "sk3", "target": "sk2", "type": "requires-output-from"},
                ],
            )

            suite_dir = assemble_suite(config, candidates, out, source="/test/pipeline")
            assert suite_dir.exists()
            assert (suite_dir / "suite.yaml").exists()

            # Verify each sub-skill has its ontology relations populated
            import yaml
            for skill_name, expected_target in [
                ("data-fetcher-skill", None),       # Producer — no upstream
                ("data-cleaner-skill", "sk1"),       # Requires sk1 output
                ("data-reporter-skill", "sk2"),      # Requires sk2 output
            ]:
                skill_yaml = suite_dir / skill_name / "skill.yaml"
                assert skill_yaml.exists(), f"Missing {skill_yaml}"
                data = yaml.safe_load(skill_yaml.read_text(encoding="utf-8"))
                if expected_target:
                    rels = data.get("ontology", {}).get("relations", [])
                    assert any(
                        r["type"] == "requires-output-from" and r["target"] == expected_target
                        for r in rels
                    ), f"{skill_name} missing requires-output-from → {expected_target}"

    def test_pipeline_topological_order(self):
        """Skills in a requires-output-from chain must be topologically sortable.

        This verifies that a data pipeline can be executed in dependency order:
        producer first, then intermediate stages, then final consumers.
        """
        # Pipeline: sk1 (fetch) → sk2 (clean) → sk3 (report)
        # sk2 requires-output-from sk1, sk3 requires-output-from sk2
        relations = [
            {"source": "sk2", "target": "sk1", "type": "requires-output-from"},
            {"source": "sk3", "target": "sk2", "type": "requires-output-from"},
        ]

        # Validate DAG first
        valid, _ = validate_dag(relations)
        assert valid is True

        # Topological sort (Kahn's algorithm)
        nodes = {"sk1", "sk2", "sk3"}
        in_degree: dict[str, int] = {n: 0 for n in nodes}
        adj: dict[str, set[str]] = {n: set() for n in nodes}
        for r in relations:
            adj[r["target"]].add(r["source"])  # target → source (upstream)
            in_degree[r["source"]] += 1

        queue = [n for n in nodes if in_degree[n] == 0]
        order = []
        while queue:
            node = queue.pop(0)
            order.append(node)
            for downstream in adj[node]:
                in_degree[downstream] -= 1
                if in_degree[downstream] == 0:
                    queue.append(downstream)

        assert len(order) == 3, f"Incomplete pipeline: {order}"
        # sk1 (fetch) must come first, sk3 (report) last
        assert order[0] == "sk1", f"Expected sk1 first, got {order}"
        assert order[-1] == "sk3", f"Expected sk3 last, got {order}"

    def test_mixed_relation_types_pipeline(self):
        """Pipeline with mixed depends-on + requires-output-from validates correctly."""
        relations = [
            {"source": "sk2", "target": "sk1", "type": "requires-output-from"},
            {"source": "sk3", "target": "sk2", "type": "depends-on"},
        ]
        # Both are directional → should form a chain
        valid, _ = validate_dag(relations)
        assert valid is True

        # Make it cyclic
        relations.append({"source": "sk1", "target": "sk3", "type": "depends-on"})
        valid, msg = validate_dag(relations)
        assert valid is False
        assert "cycle" in msg.lower()


class TestSkillOverlap:
    """Tests for SkillNet overlap detection (paper §8.3)."""

    def test_identical_skills_detected(self):
        """Two skills with the same steps should be flagged as overlapping."""
        c1 = make_skill("sk1", name="Formatter A", steps=["Read file", "Format text", "Write file"])
        c2 = make_skill("sk2", name="Formatter B", steps=["Read file", "Format text", "Write file"])
        overlaps = detect_skill_overlap([c1, c2], threshold=0.5)
        assert len(overlaps) == 1
        assert overlaps[0]["similarity"] > 0.5

    def test_completely_different_skills_not_flagged(self):
        """Skills with non-overlapping functionality should pass."""
        c1 = make_skill("sk1", name="Formatter", steps=["Read file", "Format text", "Write file"])
        c2 = make_skill("sk2", name="Database", steps=["Connect to DB", "Execute query", "Return results"])
        overlaps = detect_skill_overlap([c1, c2], threshold=0.5)
        assert len(overlaps) == 0

    def test_partial_overlap_below_threshold(self):
        """Partial overlap below threshold should not be flagged."""
        c1 = make_skill("sk1", name="A", steps=["Read file", "Format text", "Write output"])
        c2 = make_skill("sk2", name="B", steps=["Read input", "Process data", "Write file"])
        # Only "file" overlaps → similarity should be low
        overlaps = detect_skill_overlap([c1, c2], threshold=0.5)
        assert len(overlaps) == 0

    def test_dependencies_contribute_to_overlap(self):
        """Shared dependencies should increase overlap score."""
        c1 = make_skill(
            "sk1", name="A",
            steps=["Process data"],
            dependencies=["numpy", "pandas"],
        )
        c2 = make_skill(
            "sk2", name="B",
            steps=["Analyze data"],
            dependencies=["numpy", "pandas"],
        )
        overlaps = detect_skill_overlap([c1, c2], threshold=0.3)
        assert len(overlaps) == 1

    def test_high_threshold_filters_more(self):
        """A very high threshold should filter out partial overlaps."""
        c1 = make_skill("sk1", steps=["Read file", "Format text", "Write file"])
        c2 = make_skill("sk2", steps=["Read file", "Format text", "Write output"])
        # 0.99 threshold should filter out even high-overlap pairs
        overlaps = detect_skill_overlap([c1, c2], threshold=0.99)
        assert len(overlaps) == 0

    def test_overlapping_terms_in_result(self):
        """Result should include the specific overlapping terms."""
        c1 = make_skill("sk1", name="Formatter", steps=["Read input", "Format text"])
        c2 = make_skill("sk2", name="Cleaner", steps=["Read input", "Clean text"])
        overlaps = detect_skill_overlap([c1, c2], threshold=0.3)
        assert len(overlaps) == 1
        assert "input" in overlaps[0]["overlapping_terms"]
        assert "text" in overlaps[0]["overlapping_terms"]
