"""G1 static security scan (design.md §4.2).

Deterministic regex/AST-based scan for dangerous patterns in generated skill
scripts. No LLM involved — this is a pure static analysis pass.

Checks for:
  - eval / exec (arbitrary code execution)
  - socket (network access)
  - subprocess / os.system / os.popen (command injection surface)
  - shutil.rmtree / os.remove / os.unlink (destructive file operations)
  - Jinja2 |safe filter (XSS in templates)
"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path

from repo2skill.models import G1Report

logger = logging.getLogger(__name__)

# Patterns: (regex, description, severity)
DANGEROUS_PATTERNS: list[tuple[str, str, str]] = [
    # Arbitrary code execution
    (r"\beval\s*\(", "eval() call — arbitrary code execution", "high"),
    (r"\bexec\s*\(", "exec() call — arbitrary code execution", "high"),
    (r"\bcompile\s*\(.*\)", "compile() with dynamic source — code injection risk", "medium"),
    # Network access
    (r"\bsocket\s*\.", "socket usage — network access", "high"),
    (r"\burllib\.request\b", "urllib.request — outbound HTTP", "medium"),
    (r"\brequests\s*\.\b", "requests library — outbound HTTP", "medium"),
    (r"\bhttp\.client\b", "http.client — outbound HTTP", "medium"),
    # Command execution
    (r"\bsubprocess\s*\.", "subprocess call — command execution", "high"),
    (r"\bos\.system\s*\(", "os.system() — command injection surface", "high"),
    (r"\bos\.popen\s*\(", "os.popen() — command injection surface", "high"),
    (r"\bcommands\.getoutput\b", "commands.getoutput() — removed in Python 3, insecure", "high"),
    # Destructive file operations
    (r"\bshutil\.rmtree\s*\(", "shutil.rmtree() — recursive deletion", "high"),
    (r"\bos\.remove\s*\(", "os.remove() — file deletion", "medium"),
    (r"\bos\.unlink\s*\(", "os.unlink() — file deletion", "medium"),
    (r"\bshutil\.move\s*\(", "shutil.move() — file relocation", "low"),
    # Template injection
    (r"\|[\s]*safe[\s]*[\}\n]", "Jinja2 |safe filter — XSS risk", "high"),
    (r"\|[\s]*escape[\s]*[\}\n]", "Jinja2 |escape — review required", "low"),
    # Dynamic imports
    (r"\bimportlib\.import_module\s*\(", "importlib.import_module() — dynamic import", "medium"),
    (r"\b__import__\s*\(", "__import__() — dynamic import", "medium"),
    # Hardcoded paths — repository-specific, not portable (paper §3.3.3)
    (r"/(?:home|Users|tmp|var|etc|opt|usr)/", "hardcoded absolute path — not portable", "medium"),
    (r"[A-Za-z]:[/\\]", "hardcoded Windows drive-letter path — not portable", "medium"),
    # Suspicious secret-like variable assignments (paper §7)
    (r"(?i)(api[_-]?key|secret|token|password|passwd)\s*=\s*\"[^\"]{20,}\"",
     "variable named like a secret with a long string value — potential embedded credential", "high"),
    (r"(?i)(api[_-]?key|secret|token|password|passwd)\s*=\s*'[^']{20,}'",
     "variable named like a secret with a long string value — potential embedded credential", "high"),
    # Environment variable access with secret-like keys (paper §7, G4)
    (r"""(?i)os\.(?:environ|getenv)\s*\(\s*['\"]\s*.*(?:key|secret|token|password|pass)""",
     "env var read with secret-like key name", "low"),
]


def run_g1_scan(skill_dir: Path) -> G1Report:
    """Scan all Python files in a skill directory for dangerous patterns.

    Args:
        skill_dir: Path to the assembled skill directory.

    Returns:
        G1Report with findings and pass/fail status.
    """
    skill_name = skill_dir.name
    findings: list[dict] = []

    py_files = list(skill_dir.rglob("*.py"))
    if not py_files:
        return G1Report(skill_name=skill_name, passed=True, findings=[])

    for py_file in py_files:
        try:
            source = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        lines = source.splitlines()

        for pattern, description, severity in DANGEROUS_PATTERNS:
            for i, line in enumerate(lines, start=1):
                if re.search(pattern, line):
                    # Suppress false positives in comments
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    findings.append(
                        {
                            "pattern": pattern,
                            "description": description,
                            "file": str(py_file.relative_to(skill_dir)),
                            "line": i,
                            "severity": severity,
                            "snippet": stripped[:120],
                        }
                    )

    # Also do an AST-level check for eval/exec in non-comment code
    _ast_scan(py_files, skill_dir, findings)

    # De-duplicate findings
    seen = set()
    unique_findings = []
    for f in findings:
        key = (f["file"], f["line"], f["pattern"])
        if key not in seen:
            seen.add(key)
            unique_findings.append(f)

    # G1 passes if no "high" severity findings
    high_findings = [f for f in unique_findings if f["severity"] == "high"]
    passed = len(high_findings) == 0

    # vulnerability_rate = files with findings / total files scanned
    files_with_findings = len({f["file"] for f in unique_findings})
    vulnerability_rate = files_with_findings / max(len(py_files), 1)

    if not passed:
        logger.warning("G1 scan found %d high-severity issue(s)", len(high_findings))
        for f in high_findings:
            logger.warning("  %s:%d — %s", f["file"], f["line"], f["description"])

    return G1Report(
        skill_name=skill_name,
        passed=passed,
        findings=unique_findings,
        vulnerability_rate=round(vulnerability_rate, 2),
    )


def _ast_scan(py_files: list[Path], skill_dir: Path, findings: list[dict]) -> None:
    """AST-level scan to catch eval/exec that regex might miss."""
    for py_file in py_files:
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = _get_call_name(node)
                if func_name in ("eval", "exec"):
                    findings.append(
                        {
                            "pattern": rf"\b{func_name}\s*\(",
                            "description": f"{func_name}() call — arbitrary code execution (AST detected)",
                            "file": str(py_file.relative_to(skill_dir)),
                            "line": node.lineno,
                            "severity": "high",
                            "snippet": ast.unparse(node) if hasattr(ast, "unparse") else f"{func_name}(...)",
                        }
                    )


def _get_call_name(node: ast.Call) -> str:
    """Extract the function name from an AST Call node."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""
