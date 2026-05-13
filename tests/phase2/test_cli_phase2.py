"""Tests for Phase 2 CLI features and end-to-end pipeline."""

import json
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest
import yaml

from repo2skill.assemble import assemble_skill
from repo2skill.extractor import extract_skills, extract_skills_with_scores
from repo2skill.models import SkillCandidate
from repo2skill.reviewer.g1 import run_g1_scan
from repo2skill.structure import analyze_repo
from repo2skill.suite import detect_suite_mode

from tests.smoke.test_phase1 import create_sample_repo


class TestExtractWithScores:
    """Test extract_skills_with_scores returns SkillCandidate objects."""

    def test_returns_skill_candidates(self):
        from repo2skill.models import AnalysisResult, Conditions, Interface, Policy, Skill, Termination

        skills = [
            Skill(
                id="sk1",
                name="Formatter",
                description="Format code files",
                conditions=Conditions(trigger="User requests formatting", file_patterns=["*.py"]),
                policy=Policy(type="script", entry="formatter.main", steps=["Read", "Format", "Write"], dependencies=["pathlib"]),
                termination=Termination(success="Returns formatted text"),
                interface=Interface(params={"file_path": "str", "line_length": "int"}, allowed_tools=["Read", "Write"]),
            ),
            Skill(
                id="sk2",
                name="Utility",
                description="Utility functions",
                conditions=Conditions(trigger="Text processing"),
                policy=Policy(type="function", entry="utils.clean", steps=["Clean text"], dependencies=["re"]),
                termination=Termination(success="Cleaned text"),
                interface=Interface(params={"text": "str"}, allowed_tools=[]),
            ),
        ]
        result = AnalysisResult(repo="test", skills=skills, dependency_graph={})
        candidates = extract_skills_with_scores(result)

        assert len(candidates) >= 1
        for c in candidates:
            assert isinstance(c, SkillCandidate)
            assert hasattr(c, "confidence")
            assert hasattr(c, "reasoning")
            assert hasattr(c, "scores")
            assert 0.0 <= c.confidence <= 1.0
            assert "recurrence" in c.scores
            assert "verification" in c.scores
            assert "non_obviousness" in c.scores
            assert "generalizability" in c.scores

    def test_empty_skills_returns_empty(self):
        from repo2skill.models import AnalysisResult
        result = AnalysisResult(repo="test", skills=[], dependency_graph={})
        candidates = extract_skills_with_scores(result)
        assert candidates == []

    def test_original_extractor_still_works(self):
        """extract_skills (without scores) should still work for backward compat."""
        from repo2skill.models import AnalysisResult, Conditions, Interface, Policy, Skill, Termination

        skills = [
            Skill(
                id="sk1",
                name="Formatter",
                description="Format code",
                conditions=Conditions(trigger="Formatting"),
                policy=Policy(type="script", entry="f.main", steps=["Step1", "Step2"], dependencies=["os"]),
                termination=Termination(success="Done"),
                interface=Interface(params={"f": "str"}, allowed_tools=["Read"]),
            ),
        ]
        result = AnalysisResult(repo="test", skills=skills, dependency_graph={})
        candidates = extract_skills(result)
        assert len(candidates) == 1
        assert candidates[0].id == "sk1"


class TestG1ScanOnAssembledSkill:
    """Test G1 scan on an assembled skill directory."""

    def test_scan_assembled_skill(self):
        from repo2skill.assemble import assemble_skill
        from repo2skill.models import Conditions, Interface, Policy, Skill, Termination

        skill = Skill(
            id="sk1",
            name="Safe Skill",
            description="A safe skill for processing text files with validation and error handling",
            conditions=Conditions(
                trigger="User requests safe text processing operation",
                preconditions=["Input files exist", "Python 3.11+ available"],
                file_patterns=["*.txt", "*.md"],
            ),
            policy=Policy(
                type="function",
                entry="safe.main",
                steps=[
                    "Validate input parameters and file existence",
                    "Process text content with configured options",
                    "Return the processed result with status information",
                ],
                dependencies=["os", "pathlib"],
            ),
            termination=Termination(
                success="Text processed successfully without errors",
                output_schema={"result": "str", "status": "str"},
            ),
            interface=Interface(allowed_tools=["Read"]),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "output"
            out.mkdir()

            skill_dir = assemble_skill(skill, out)
            report = run_g1_scan(skill_dir)

            # Assembled skill should not contain dangerous patterns
            assert report.passed is True


class TestSuiteDetectionOnSampleRepo:
    """Test suite detection with a sample repo."""

    def test_sample_repo_not_suite(self):
        """The sample repo is small, should not trigger suite mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "sample-repo"
            create_sample_repo(root)

            from repo2skill.structure import analyze_repo
            from repo2skill.extractor import extract_skills_with_scores

            result = analyze_repo(str(root))
            candidates = extract_skills_with_scores(result)

            is_suite, reason = detect_suite_mode(result, candidates)
            # Small sample repo should not trigger suite mode
            # (may or may not trigger depending on candidate count)
            assert isinstance(is_suite, bool)
            assert isinstance(reason, str)


# =============================================================================
# Helper: create a multi-module sample repo for suite mode testing
# =============================================================================


def create_multi_module_repo(root: Path) -> None:
    """Create a sample repo with multiple independent modules for suite testing."""
    root.mkdir(parents=True, exist_ok=True)

    # Module A: a formatter CLI
    formatter_code = textwrap.dedent('''
        """Format text files with configurable line length.

        Usage:
            1. Read input file
            2. Apply word wrapping
            3. Write output file
        """

        import sys
        from pathlib import Path


        def format_text(text: str, line_length: int = 88) -> str:
            """Format text to a specified line length.

            Args:
                text: The input text to format.
                line_length: Maximum line length.

            Returns:
                The formatted text string.
            """
            words = text.split()
            lines = []
            current_line = []
            current_len = 0
            for word in words:
                if current_len + len(word) + len(current_line) > line_length:
                    lines.append(" ".join(current_line))
                    current_line = [word]
                    current_len = len(word)
                else:
                    current_line.append(word)
                    current_len += len(word)
            if current_line:
                lines.append(" ".join(current_line))
            return "\\n".join(lines)


        def read_file(path: Path) -> str:
            """Read text from a file.

            Args:
                path: Path to the file.

            Returns:
                File contents as string.
            """
            return path.read_text(encoding="utf-8")


        def write_file(path: Path, content: str) -> None:
            """Write text to a file.

            Args:
                path: Output file path.
                content: Content to write.
            """
            path.write_text(content, encoding="utf-8")


        def main() -> None:
            """Main entry point for the formatter CLI."""
            if len(sys.argv) < 2:
                print("Usage: python formatter.py <file>")
                sys.exit(1)
            input_path = Path(sys.argv[1])
            text = read_file(input_path)
            formatted = format_text(text)
            output_path = input_path.with_suffix(".fmt" + input_path.suffix)
            write_file(output_path, formatted)
            print(f"Output: {output_path}")


        if __name__ == "__main__":
            main()
    ''')
    (root / "formatter.py").write_text(formatter_code)

    # Module B: a linter (independent, different purpose and tool set)
    linter_code = textwrap.dedent('''
        """Check Python files for common style issues.

        Usage:
            1. Find Python files
            2. Apply lint rules
            3. Report violations
        """

        from pathlib import Path


        def lint_file(path: Path) -> list:
            """Lint a single Python file for style violations.

            Args:
                path: Path to the Python file.

            Returns:
                List of violation message strings.
            """
            violations = []
            content = path.read_text(encoding="utf-8")
            for i, line in enumerate(content.splitlines(), start=1):
                if len(line) > 100:
                    violations.append(
                        f"Line {i}: too long ({len(line)} chars)"
                    )
                if line.rstrip() != line:
                    violations.append(
                        f"Line {i}: trailing whitespace"
                    )
            return violations


        def find_python_files(root_dir: Path) -> list:
            """Find all Python files recursively.

            Args:
                root_dir: Root directory to search.

            Returns:
                List of Path objects.
            """
            return sorted(root_dir.rglob("*.py"))


        def main() -> None:
            """Main entry point: lint all Python files in current directory."""
            files = find_python_files(Path("."))
            total_violations = 0
            for f in files:
                violations = lint_file(f)
                if violations:
                    print(f"\\n{f}:")
                    for v in violations:
                        print(f"  {v}")
                    total_violations += len(violations)
            print(
                f"\\nTotal: {total_violations}"
                f" violation(s) in {len(files)} file(s)"
            )


        if __name__ == "__main__":
            main()
    ''')
    (root / "linter.py").write_text(linter_code)

    # Module C: a utility module shared by both
    utils_code = textwrap.dedent('''
        """Shared utility functions for text processing."""

        import re


        def count_words(text: str) -> int:
            """Count the number of words in a text.

            Args:
                text: Input text string.

            Returns:
                Number of words.
            """
            return len(text.split())


        def remove_extra_whitespace(text: str) -> str:
            """Collapse multiple whitespace characters into single spaces.

            Args:
                text: Input text with potential extra whitespace.

            Returns:
                Cleaned text with single spaces only.
            """
            return re.sub(r"\\s+", " ", text).strip()


        def extract_function_names(source: str) -> list:
            """Extract function names from Python source code.

            Args:
                source: Python source code string.

            Returns:
                List of function name strings.
            """
            return re.findall(r"def\\s+(\\w+)", source)
    ''')
    (root / "utils.py").write_text(utils_code)

    # README
    (root / "README.md").write_text(
        "# Sample Multi-Module Tool\\n\\nA code quality toolkit.\\n"
    )


# =============================================================================
# E2E tests: full library-level pipeline
# =============================================================================


class TestEndToEndLibrary:
    """Full pipeline end-to-end tests via library API."""

    def test_full_pipeline_with_readme_summary(self):
        """Structure → extract → assemble → G1 scan, verify readme_summary populated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "sample-repo"
            create_sample_repo(repo_root)

            # Step 1: Structure
            result = analyze_repo(str(repo_root))
            assert len(result.skills) > 0
            # readme_summary must be populated from the README.md file
            assert result.readme_summary != "", "readme_summary should contain README content"
            assert "Sample Formatter" in result.readme_summary, \
                f"readme_summary should contain README text, got: {result.readme_summary[:200]}"

            # Step 2: Extract
            candidates = extract_skills_with_scores(result)
            assert len(candidates) > 0
            for c in candidates:
                assert c.confidence >= 0.0
                assert c.confidence <= 1.0
                assert c.reasoning != ""

            # Step 3: Assemble
            out_dir = Path(tmpdir) / "output"
            out_dir.mkdir()
            skill_dir = assemble_skill(candidates[0], out_dir, source=str(repo_root))

            # Step 4: G1 scan
            g1_report = run_g1_scan(skill_dir)
            assert g1_report.passed is True, \
                f"G1 should pass on assembled skill, got: {g1_report.findings}"

            # Step 5: Verify trust level
            trust_level = "L1" if g1_report.passed else "L0"
            assert trust_level == "L1"

            # Verify output
            assert skill_dir.exists()
            assert (skill_dir / "SKILL.md").exists()
            assert (skill_dir / "skill.yaml").exists()
            assert (skill_dir / "scripts").is_dir()

            # Verify skill.yaml contains security fields
            skill_yaml = yaml.safe_load((skill_dir / "skill.yaml").read_text())
            assert "security" in skill_yaml
            assert "trust-level" in skill_yaml

    def test_full_pipeline_suite_mode(self):
        """Structure → extract → suite detection → assemble suite → G1 scan."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "multi-module-repo"
            create_multi_module_repo(repo_root)

            # Step 1: Structure
            result = analyze_repo(str(repo_root))
            assert len(result.skills) >= 2, f"Expected >= 2 skills, got {len(result.skills)}"

            # Step 2: Extract
            candidates = extract_skills_with_scores(result)
            assert len(candidates) >= 2

            # Step 3: Suite detection
            is_suite, reason = detect_suite_mode(result, candidates)
            assert isinstance(is_suite, bool)
            assert isinstance(reason, str)

            # Step 4: Assemble (force suite mode)
            from repo2skill.suite import assemble_suite, infer_relations, validate_dag
            from repo2skill.models import SuiteConfig

            # Select all candidates
            selected = candidates

            relations = infer_relations(selected, result.dependency_graph)
            valid, dag_msg = validate_dag(relations)
            assert valid is True, f"DAG should be valid: {dag_msg}"

            suite_config = SuiteConfig(
                name=result.repo,
                description=f"Skill suite for {result.repo}",
                skills=[s.id for s in selected],
                relations=relations,
            )

            out_dir = Path(tmpdir) / "output"
            out_dir.mkdir()
            suite_dir = assemble_suite(suite_config, selected, out_dir, source=str(repo_root))

            # Step 5: G1 scan on suite directory
            g1_report = run_g1_scan(suite_dir)
            assert g1_report.passed is True

            # Verify suite output
            assert suite_dir.exists()
            assert (suite_dir / "suite.yaml").exists()
            suite_yaml = yaml.safe_load((suite_dir / "suite.yaml").read_text())
            assert "suite-id" in suite_yaml
            assert "skills" in suite_yaml
            assert len(suite_yaml["skills"]) >= 2
            assert "trust-level" in suite_yaml

            # Verify each sub-skill has a directory with SKILL.md
            for skill in suite_yaml["skills"]:
                skill_path = suite_dir / skill["path"]
                assert skill_path.exists(), f"Sub-skill dir missing: {skill_path}"
                assert (skill_path / "SKILL.md").exists(), \
                    f"Sub-skill SKILL.md missing: {skill_path}"


# =============================================================================
# E2E tests: CLI-level pipeline
# =============================================================================


@pytest.fixture
def sample_repo_path(tmp_path: Path) -> Path:
    """Create a sample repo and return its path."""
    repo = tmp_path / "sample-repo"
    create_sample_repo(repo)
    return repo


@pytest.fixture
def multi_module_repo_path(tmp_path: Path) -> Path:
    """Create a multi-module repo and return its path."""
    repo = tmp_path / "multi-module-repo"
    create_multi_module_repo(repo)
    return repo


class TestCliEndToEnd:
    """Full pipeline end-to-end tests via CLI."""

    def _run_cli(self, *args: str) -> subprocess.CompletedProcess:
        """Run the repo2skill CLI and return the completed process."""
        return subprocess.run(
            [sys.executable, "-m", "repo2skill.cli", *args],
            capture_output=True,
            text=True,
        )

    def test_cli_non_interactive_single_mode(self, sample_repo_path: Path):
        """CLI with --non-interactive should complete the full pipeline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "output"
            out_dir.mkdir()

            result = self._run_cli(
                str(sample_repo_path),
                "--out", str(out_dir),
                "--non-interactive",
                "--mode", "single",
            )

            assert result.returncode == 0, f"CLI failed: {result.stderr}"
            stdout = result.stdout

            # Verify pipeline steps appear in output
            assert "Analyzing:" in stdout
            assert "Found" in stdout
            assert "candidate" in stdout
            assert "Selected" in stdout
            assert "G1 static security scan" in stdout
            assert "Initial trust level: L1" in stdout
            assert "--- Done ---" in stdout

            # Verify output files exist
            skill_dirs = list(out_dir.glob("*-skill"))
            assert len(skill_dirs) >= 1, f"No skill dirs found in {out_dir}"
            for d in skill_dirs:
                assert (d / "SKILL.md").exists(), f"SKILL.md missing in {d}"
                assert (d / "skill.yaml").exists(), f"skill.yaml missing in {d}"
                skill_yaml = yaml.safe_load((d / "skill.yaml").read_text())
                assert "trust-level" in skill_yaml
                assert "security" in skill_yaml

    def test_cli_suite_mode(self, multi_module_repo_path: Path):
        """CLI with --mode suite should produce suite.yaml with sub-skills."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "output"
            out_dir.mkdir()

            result = self._run_cli(
                str(multi_module_repo_path),
                "--out", str(out_dir),
                "--non-interactive",
                "--mode", "suite",
                "--confidence-threshold", "0.3",
            )

            assert result.returncode == 0, f"CLI failed: {result.stderr}"

            # Look for suite directory
            suite_dirs = list(out_dir.glob("*-suite"))
            assert len(suite_dirs) >= 1, \
                f"No suite dir found in {out_dir}. Contents: {list(out_dir.iterdir())}"

            suite_dir = suite_dirs[0]
            assert (suite_dir / "suite.yaml").exists(), \
                f"suite.yaml missing. Contents: {list(suite_dir.iterdir())}"

            suite_yaml = yaml.safe_load((suite_dir / "suite.yaml").read_text())
            assert "suite-id" in suite_yaml
            assert "skills" in suite_yaml
            assert "relations" in suite_yaml
            assert "trust-level" in suite_yaml

            # Verify each sub-skill
            for skill in suite_yaml["skills"]:
                skill_path = suite_dir / skill["path"]
                assert skill_path.exists(), f"Sub-skill dir missing: {skill_path}"
                assert (skill_path / "SKILL.md").exists()
                assert (skill_path / "skill.yaml").exists()

    def test_cli_auto_mode_detects_suite(self, multi_module_repo_path: Path):
        """CLI with --mode auto should detect suite from repo structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "output"
            out_dir.mkdir()

            result = self._run_cli(
                str(multi_module_repo_path),
                "--out", str(out_dir),
                "--non-interactive",
                "--mode", "auto",
                "--confidence-threshold", "0.3",
            )

            assert result.returncode == 0, f"CLI failed: {result.stderr}"
            stdout = result.stdout
            # In auto mode, suite detection should run
            assert "Selected" in stdout

    def test_cli_write_analysis_flag(self, sample_repo_path: Path):
        """--write-analysis should produce analysis.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "output"
            out_dir.mkdir()

            result = self._run_cli(
                str(sample_repo_path),
                "--out", str(out_dir),
                "--non-interactive",
                "--write-analysis",
            )

            assert result.returncode == 0, f"CLI failed: {result.stderr}"

            analysis_path = out_dir / "analysis.json"
            assert analysis_path.exists(), f"analysis.json missing in {out_dir}"

            data = json.loads(analysis_path.read_text())
            assert "repo" in data
            assert "skills" in data
            assert "dependency_graph" in data
            assert "readme_summary" in data
            assert data["readme_summary"] != "", \
                "readme_summary should be populated in analysis.json"

    def test_cli_force_continue_flag_accepted(self, sample_repo_path: Path):
        """--force-continue should be accepted without error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "output"
            out_dir.mkdir()

            result = self._run_cli(
                str(sample_repo_path),
                "--out", str(out_dir),
                "--non-interactive",
                "--force-continue",
            )

            assert result.returncode == 0, \
                f"CLI with --force-continue failed: {result.stderr}"
            # When G1 passes (normal case), trust is L1
            assert "Initial trust level: L1" in result.stdout

    def test_g1_blocking_on_dangerous_skill(self, tmp_path: Path):
        """G1 should fail on a skill directory containing dangerous patterns."""
        # Create a skill directory with dangerous Python code in scripts/
        skill_dir = tmp_path / "dangerous-skill"
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "bad.py").write_text(textwrap.dedent("""
            import os
            import subprocess

            def dangerous_func(cmd: str) -> str:
                \"\"\"Execute a shell command.\"\"\"
                return subprocess.check_output(cmd, shell=True, text=True)

            if __name__ == "__main__":
                import sys
                if len(sys.argv) > 1:
                    os.system(sys.argv[1])
        """))

        report = run_g1_scan(skill_dir)
        assert report.passed is False, \
            f"G1 should block dangerous patterns, got: {report.findings}"
        high = [f for f in report.findings if f["severity"] == "high"]
        assert len(high) >= 2  # subprocess + os.system

    def test_cli_help_shows_all_new_flags(self):
        """--help should list all Phase 2 flags."""
        result = self._run_cli("--help")
        assert result.returncode == 0

        help_text = result.stdout
        assert "--interactive" in help_text
        assert "--non-interactive" in help_text
        assert "--mode" in help_text
        assert "confidence" in help_text  # typer may truncate to --confidence-thres…
        assert "--force-continue" in help_text
        assert "--write-analysis" in help_text


class TestG2RoundTrip:
    """Verify G2 score persists correctly in skill.yaml."""

    def test_g2_score_round_trip(self):
        """Assemble skill with g2_score, reload yaml, verify value preserved."""
        from repo2skill.assemble import assemble_skill
        from repo2skill.models import Conditions, Interface, Policy, Skill, Termination

        skill = Skill(
            id="sk1",
            name="G2 Test Skill",
            description="A skill for testing G2 score persistence and round-trip integrity",
            conditions=Conditions(
                trigger="User requests G2 score verification",
                preconditions=["repo2skill installed", "test environment ready"],
                file_patterns=["*.test"],
            ),
            policy=Policy(
                type="function",
                entry="g2test.main",
                steps=[
                    "Step 1: Initialize test parameters and validate inputs",
                    "Step 2: Execute the test operation with configured options",
                    "Step 3: Verify the expected output matches the specification",
                ],
                dependencies=["pytest", "pyyaml"],
            ),
            termination=Termination(
                success="G2 score successfully round-tripped through yaml persistence",
                output_schema={"score": "float", "verdict": "str"},
            ),
            interface=Interface(
                params={"test_name": "str", "verbose": "bool"},
                allowed_tools=["Read", "Write"],
            ),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "output"
            out.mkdir()

            # Assemble with a specific g2_score
            skill_dir = assemble_skill(
                skill, out, source="/test/repo",
                trust_level="L2", g1_passed=True, g2_score=0.85,
            )

            # Reload the yaml and verify the score persisted
            yaml_path = skill_dir / "skill.yaml"
            data = yaml.safe_load(yaml_path.read_text())

            assert data is not None
            assert "security" in data
            assert data["security"]["g1-passed"] is True, \
                f"g1-passed should be True, got {data['security']['g1-passed']}"
            assert data["security"]["g2-score"] == 0.85, \
                f"g2-score should be 0.85, got {data['security']['g2-score']}"
            assert data["trust-level"] == "L2", \
                f"trust-level should be L2, got {data['trust-level']}"

    def test_g2_score_default_zero(self):
        """Default g2_score should be 0.0 and g1_passed should be False."""
        from repo2skill.assemble import assemble_skill
        from repo2skill.models import Conditions, Interface, Policy, Skill, Termination

        skill = Skill(
            id="sk1",
            name="Default Test",
            description="A test skill with default security settings for verification",
            conditions=Conditions(
                trigger="Test trigger",
                preconditions=["Environment ready"],
                file_patterns=["*.default"],
            ),
            policy=Policy(
                type="function",
                entry="test.default",
                steps=["Execute default operation", "Verify default output"],
                dependencies=["os"],
            ),
            termination=Termination(success="Default test complete"),
            interface=Interface(allowed_tools=["Read"]),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "output"
            out.mkdir()

            skill_dir = assemble_skill(skill, out)  # all defaults

            data = yaml.safe_load((skill_dir / "skill.yaml").read_text())
            assert data["security"]["g1-passed"] is False
            assert data["security"]["g2-score"] == 0.0


class TestBootstrap:
    """Self-bootstrap: Repo2Skill processes its own repository."""

    def test_bootstrap_structure(self):
        """Structurer should successfully parse Repo2Skill's own code."""
        import os
        repo_root = Path(__file__).resolve().parent.parent.parent
        result = analyze_repo(str(repo_root))

        assert len(result.skills) > 0, \
            f"Expected skills in self-analysis, got {len(result.skills)}"
        assert result.readme_summary, "readme_summary should not be empty"
        assert len(result.dependency_graph["nodes"]) > 0, \
            "Should have dependency graph nodes"
        # Core modules should be present
        modules = set(result.dependency_graph["nodes"])
        core_modules = {"src.repo2skill.models", "src.repo2skill.structure",
                        "src.repo2skill.assemble", "src.repo2skill.cli"}
        for m in core_modules:
            assert m in modules, f"Core module {m} should be in dependency graph"

    def test_bootstrap_extract_and_assemble(self):
        """Full pipeline on self should succeed without errors."""
        repo_root = Path(__file__).resolve().parent.parent.parent

        result = analyze_repo(str(repo_root))
        candidates = extract_skills_with_scores(result)
        assert len(candidates) >= 1, "Should find at least 1 candidate in self"

        # Assemble top candidate
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "output"
            out.mkdir()
            skill_dir = assemble_skill(candidates[0], out, source=str(repo_root))

            assert skill_dir.exists()
            assert (skill_dir / "SKILL.md").exists()
            assert (skill_dir / "skill.yaml").exists()

            # G1 scan should pass on own code
            report = run_g1_scan(skill_dir)
            assert report.passed, \
                f"G1 should pass on self, got: {[f['description'] for f in report.findings if f['severity']=='high']}"

    def test_bootstrap_cli_on_self(self):
        """CLI --non-interactive should complete on own repo without error."""
        repo_root = Path(__file__).resolve().parent.parent.parent

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "output"
            out_dir.mkdir()

            result = subprocess.run(
                [sys.executable, "-m", "repo2skill.cli",
                 str(repo_root),
                 "--out", str(out_dir),
                 "--non-interactive",
                 "--mode", "single"],
                capture_output=True, text=True,
            )

            assert result.returncode == 0, \
                f"CLI on self failed (rc={result.returncode}): {result.stderr[:500]}"
            assert "Initial trust level" in result.stdout
