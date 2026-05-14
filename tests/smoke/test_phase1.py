"""Phase 1 end-to-end smoke test.

Creates a tiny sample Python repo, runs repo2skill on it, and verifies
the output SKILL.md and skill.yaml.
"""

from __future__ import annotations

import json
import tempfile
import textwrap
from pathlib import Path

import pytest
import yaml

from repo2skill.assemble import assemble_skill
from repo2skill.extractor import extract_skills
from repo2skill.models import AnalysisResult, Conditions, Interface, Policy, Skill, Termination
from repo2skill.structure import analyze_repo


def create_sample_repo(root: Path) -> None:
    """Create a small sample Python repo for testing."""
    root.mkdir(parents=True, exist_ok=True)

    # A simple CLI tool module
    cli_code = textwrap.dedent('''
        """Sample CLI tool for formatting text files.

        Usage:
            1. Read the input file
            2. Apply formatting rules
            3. Write the output file
        """

        import sys
        from pathlib import Path
        from typing import Optional


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

            Raises:
                FileNotFoundError: If the file does not exist.
            """
            if not path.exists():
                raise FileNotFoundError(f"File not found: {path}")
            return path.read_text(encoding="utf-8")


        def write_file(path: Path, content: str) -> None:
            """Write text to a file.

            Args:
                path: Output file path.
                content: Content to write.
            """
            path.write_text(content, encoding="utf-8")


        def main() -> None:
            """Main entry point for the CLI."""
            if len(sys.argv) < 2:
                print("Usage: python formatter.py <file> [--line-length N]")
                sys.exit(1)

            input_path = Path(sys.argv[1])
            line_length = 88

            for i, arg in enumerate(sys.argv):
                if arg == "--line-length" and i + 1 < len(sys.argv):
                    line_length = int(sys.argv[i + 1])

            text = read_file(input_path)
            formatted = format_text(text, line_length)
            output_path = input_path.with_suffix(".fmt" + input_path.suffix)
            write_file(output_path, formatted)
            print(f"Formatted output written to: {output_path}")


        if __name__ == "__main__":
            main()
    ''')

    (root / "formatter.py").write_text(cli_code)

    # A utility module
    utils_code = textwrap.dedent('''
        """Utility functions for text processing."""

        import re


        def count_words(text: str) -> int:
            """Count the number of words in a text."""
            return len(text.split())


        def remove_extra_whitespace(text: str) -> str:
            """Collapse multiple whitespace characters into single spaces."""
            return re.sub(r"\\s+", " ", text).strip()
    ''')

    (root / "utils.py").write_text(utils_code)

    # README
    readme = textwrap.dedent('''
        # Sample Formatter

        A simple text formatting tool for Python.

        ## Usage

        ```bash
        python formatter.py myfile.txt --line-length 100
        ```

        ## Features

        - Word wrapping at configurable line length
        - File I/O with error handling
        - Utility functions for text processing
    ''')

    (root / "README.md").write_text(readme)


class TestAnalyzeRepo:
    """Tests for the structurer (P1-T3+T4)."""

    def test_analyze_sample_repo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "sample-repo"
            create_sample_repo(root)

            result = analyze_repo(str(root))

            assert isinstance(result, AnalysisResult)
            assert result.repo == "sample-repo"
            assert len(result.skills) >= 1

            # Each skill should have the four tuples populated
            for skill in result.skills:
                assert skill.conditions is not None
                assert skill.policy is not None
                assert skill.termination is not None
                assert skill.interface is not None

            # At least one skill should have steps extracted
            skills_with_steps = [s for s in result.skills if s.policy.steps]
            assert len(skills_with_steps) > 0

    def test_dependency_graph(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "sample-repo"
            create_sample_repo(root)

            result = analyze_repo(str(root))

            assert "nodes" in result.dependency_graph
            assert "edges" in result.dependency_graph
            assert len(result.dependency_graph["nodes"]) > 0


class TestExtractor:
    """Tests for the extractor (P1-T5)."""

    def test_extract_returns_candidates(self):
        skills = [
            Skill(
                id="sk1",
                name="Python Code Formatter",
                description="Format Python files",
                conditions=Conditions(triggers=["User requests formatting"], file_patterns=["*.py"]),
                policy=Policy(type="script", entry="formatter.main", steps=["Read", "Format", "Write"], dependencies=["pathlib"]),
                termination=Termination(success="Returns formatted text"),
                interface=Interface(params={"file_path": "str", "line_length": "int"}, allowed_tools=["Read", "Write"]),
            ),
            Skill(
                id="sk2",
                name="Utility",
                description="Utility functions",
                conditions=Conditions(triggers=["Text processing needed"]),
                policy=Policy(type="function", entry="utils.remove_whitespace", steps=["Remove whitespace"], dependencies=["re"]),
                termination=Termination(success="Returns cleaned text"),
                interface=Interface(params={"text": "str"}, allowed_tools=[]),
            ),
        ]

        result = AnalysisResult(repo="test", skills=skills, dependency_graph={})
        candidates = extract_skills(result)

        assert len(candidates) >= 1
        assert len(candidates) <= 5
        # First candidate should be the highest-scoring one
        assert candidates[0].id == "sk1"  # Complex script > simple utility


class TestAssemble:
    """Tests for the assembler (P1-T7)."""

    def test_assemble_creates_output(self):
        skill = Skill(
            id="sk1",
            name="Test Formatter",
            description="Format test files with configurable line length and indentation style for Python source code",
            conditions=Conditions(
                triggers=["User requests text formatting with specific style and formatting preferences"],
                preconditions=["Python files exist in workspace", "black formatter installed"],
                file_patterns=["*.txt", "*.md", "*.py"],
            ),
            policy=Policy(
                type="script",
                entry="formatter.main",
                steps=[
                    "Read input file from the specified path and validate it exists",
                    "Apply formatting rules including line wrapping and indentation",
                    "Write the formatted output to the destination file",
                ],
                dependencies=["pathlib", "typer"],
            ),
            termination=Termination(
                success="Formatted output written successfully with exit code 0",
                output_schema={"status": "formatted", "files_processed": "int"},
            ),
            interface=Interface(
                params={"file_path": "Path", "line_length": "int", "style": "str"},
                allowed_tools=["Read", "Write"],
            ),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            skill_dir = assemble_skill(skill, out, source="/test/repo")

            assert skill_dir.exists()
            assert (skill_dir / "SKILL.md").exists()
            assert (skill_dir / "skill.yaml").exists()
            assert (skill_dir / "scripts").is_dir()
            assert (skill_dir / "references").is_dir()
            assert (skill_dir / "templates").is_dir()
            assert (skill_dir / "verification").is_dir()

    def test_skill_md_is_valid_markdown(self):
        skill = Skill(
            id="sk1",
            name="Test Skill",
            description="A test skill for formatting Python source code with configurable options for line length and indentation style",
            conditions=Conditions(
                triggers=["User requests code formatting with specific style preferences"],
                preconditions=["Python files exist in workspace", "black formatter installed"],
                file_patterns=["*.py", "*.pyi"],
            ),
            policy=Policy(
                type="function",
                entry="test.main",
                steps=[
                    "Step 1: Read the input Python files from the specified directory",
                    "Step 2: Parse each file to identify formatting issues",
                    "Step 3: Apply formatting rules to fix line length, indentation, and spacing",
                    "Step 4: Write the formatted output back to the files",
                ],
                dependencies=["os", "pathlib", "black"],
            ),
            termination=Termination(
                success="All files formatted successfully with exit code 0",
                output_schema={"status": "formatted", "files_processed": "int"},
            ),
            interface=Interface(params={"x": "int", "y": "str"}, allowed_tools=["Read", "Write"]),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            skill_dir = assemble_skill(skill, out)

            md_content = (skill_dir / "SKILL.md").read_text()

            # Must have YAML frontmatter
            assert md_content.startswith("---")
            # Should have the four-tuple sections
            assert "## Conditions" in md_content
            assert "## Policy" in md_content
            assert "## Termination" in md_content
            assert "## Interface" in md_content
            assert "## Security" in md_content

    def test_skill_yaml_is_valid_yaml(self):
        skill = Skill(
            id="sk1",
            name="Test Skill",
            description="A reusable test skill that demonstrates the four-tuple decomposition with proper documentation of conditions, policy steps, termination criteria, and interface parameters",
            conditions=Conditions(
                triggers=["User requests the test operation with required parameters"],
                preconditions=["Python 3.11+ installed", "Required packages available"],
                file_patterns=["*.py", "*.txt"],
            ),
            policy=Policy(
                type="function",
                entry="test.main",
                steps=[
                    "Step 1: Validate all input parameters and preconditions",
                    "Step 2: Execute the core operation with configured options",
                    "Step 3: Collect and format the operation results",
                ],
                dependencies=["os", "pathlib"],
            ),
            termination=Termination(
                success="Operation completed successfully with expected output",
                output_schema={"result": "str", "status_code": "int"},
            ),
            interface=Interface(
                params={"x": "int", "verbose": "bool"},
                allowed_tools=["Read", "Write"],
            ),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            skill_dir = assemble_skill(skill, out)

            yaml_content = yaml.safe_load((skill_dir / "skill.yaml").read_text())

            assert yaml_content is not None
            assert "name" in yaml_content
            assert "version" in yaml_content
            assert "trust-level" in yaml_content
            assert "security" in yaml_content
            assert "ontology" in yaml_content


class TestSmokeEndToEnd:
    """End-to-end smoke test (P1-T9)."""

    def test_full_pipeline(self):
        """Run the complete pipeline on a sample repo and verify output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "sample-repo"
            create_sample_repo(repo_root)

            # Step 1: Analyze
            result = analyze_repo(str(repo_root))
            assert len(result.skills) > 0

            # Step 2: Extract
            candidates = extract_skills(result)
            assert len(candidates) > 0

            # Step 3: Assemble
            out_dir = Path(tmpdir) / "output"
            out_dir.mkdir()
            skill_dir = assemble_skill(candidates[0], out_dir, source=str(repo_root))

            # Verify output
            assert skill_dir.exists()
            md_file = skill_dir / "SKILL.md"
            yaml_file = skill_dir / "skill.yaml"

            assert md_file.exists(), f"SKILL.md not found at {md_file}"
            assert yaml_file.exists(), f"skill.yaml not found at {yaml_file}"

            # Check markdown content
            md_content = md_file.read_text()
            assert "---" in md_content  # frontmatter delimiter

            # Check yaml content
            yaml_content = yaml.safe_load(yaml_file.read_text())
            assert isinstance(yaml_content, dict)

    def test_pipeline_on_empty_dir(self):
        """Pipeline should handle a directory with no Python files gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            empty = Path(tmpdir) / "empty-repo"
            empty.mkdir()

            result = analyze_repo(str(empty))
            assert result.skills == []
