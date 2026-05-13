"""Tests for G1 static security scan."""

import tempfile
from pathlib import Path

from repo2skill.reviewer.g1 import run_g1_scan


def write_script(skill_dir: Path, filename: str, content: str) -> Path:
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    p = scripts_dir / filename
    p.write_text(content)
    return p


class TestG1Scan:
    def test_clean_skill_passes(self):
        """A skill with no dangerous patterns should pass."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "clean-skill"
            write_script(skill_dir, "main.py", "print('hello world')\n")

            report = run_g1_scan(skill_dir)
            assert report.passed is True
            assert report.skill_name == "clean-skill"

    def test_empty_skill_passes(self):
        """A skill with no Python files should pass."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "empty-skill"
            skill_dir.mkdir()

            report = run_g1_scan(skill_dir)
            assert report.passed is True

    def test_eval_detected(self):
        """eval() should be flagged as high severity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "dangerous-skill"
            write_script(skill_dir, "bad.py", "result = eval(user_input)\n")

            report = run_g1_scan(skill_dir)
            assert report.passed is False
            high = [f for f in report.findings if f["severity"] == "high"]
            assert len(high) >= 1
            assert any("eval" in f["description"] for f in high)

    def test_exec_detected(self):
        """exec() should be flagged as high severity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "dangerous-skill"
            write_script(skill_dir, "bad.py", "exec(code_string)\n")

            report = run_g1_scan(skill_dir)
            high = [f for f in report.findings if f["severity"] == "high"]
            assert any("exec" in f["description"] for f in high)

    def test_subprocess_detected(self):
        """subprocess usage should be flagged as high severity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "dangerous-skill"
            write_script(skill_dir, "bad.py", "import subprocess\nsubprocess.run(['rm', '-rf', '/'])\n")

            report = run_g1_scan(skill_dir)
            assert report.passed is False
            high = [f for f in report.findings if f["severity"] == "high"]
            assert any("subprocess" in f["description"] for f in high)

    def test_os_system_detected(self):
        """os.system() should be flagged as high severity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "dangerous-skill"
            write_script(skill_dir, "bad.py", "import os\nos.system('rm -rf /')\n")

            report = run_g1_scan(skill_dir)
            high = [f for f in report.findings if f["severity"] == "high"]
            assert any("os.system" in f["description"] for f in high)

    def test_shutil_rmtree_detected(self):
        """shutil.rmtree() should be flagged as high severity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "dangerous-skill"
            write_script(skill_dir, "bad.py", "import shutil\nshutil.rmtree('/tmp/data')\n")

            report = run_g1_scan(skill_dir)
            high = [f for f in report.findings if f["severity"] == "high"]
            assert any("rmtree" in f["description"] for f in high)

    def test_socket_detected(self):
        """socket usage should be flagged as high severity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "dangerous-skill"
            write_script(skill_dir, "bad.py", "import socket\ns = socket.socket()\ns.connect(('evil.com', 80))\n")

            report = run_g1_scan(skill_dir)
            high = [f for f in report.findings if f["severity"] == "high"]
            assert any("socket" in f["description"] for f in high)

    def test_jinja2_safe_filter_detected(self):
        """Jinja2 |safe filter should be flagged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "dangerous-skill"
            write_script(skill_dir, "bad.py", "template = '{{ content | safe }}'\n")

            report = run_g1_scan(skill_dir)
            high = [f for f in report.findings if f["severity"] == "high"]
            assert any("safe" in f["description"] for f in high)

    def test_comment_suppression(self):
        """Comments mentioning dangerous functions should not be flagged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "safe-skill"
            write_script(skill_dir, "main.py", "# This script never calls eval() or exec()\nprint('safe')\n")

            report = run_g1_scan(skill_dir)
            # Comments are suppressed, should not flag
            high = [f for f in report.findings if f["severity"] == "high"]
            assert len(high) == 0

    def test_requests_detected_as_medium(self):
        """requests library should be flagged as medium."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "network-skill"
            write_script(skill_dir, "main.py", "import requests\nr = requests.get('https://api.example.com')\n")

            report = run_g1_scan(skill_dir)
            # Medium findings don't cause failure
            assert report.passed is True
            medium = [f for f in report.findings if f["severity"] == "medium"]
            assert any("requests" in f["description"] for f in medium)

    def test_multiple_files(self):
        """Scan should cover all Python files in the skill dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "multi-skill"
            write_script(skill_dir, "clean.py", "print('safe')\n")
            write_script(skill_dir, "dangerous.py", "eval(input())\n")
            # Also test nested dir
            nested = skill_dir / "scripts" / "utils"
            nested.mkdir(parents=True, exist_ok=True)
            (nested / "bad.py").write_text("exec(code)\n")

            report = run_g1_scan(skill_dir)
            assert report.passed is False
            high = [f for f in report.findings if f["severity"] == "high"]
            # Both eval and exec across different files
            assert len(high) >= 2
