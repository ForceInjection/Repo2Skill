"""Structurer: repo clone, AST parse, dependency graph, four-tuple pre-annotation.

Uses Python's stdlib `ast` module for Phase 1. Will migrate to `tree-sitter`
in Phase 4 when adding multi-language support.
"""

from __future__ import annotations

import ast
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from repo2skill.models import (
    AnalysisResult,
    Conditions,
    Interface,
    Policy,
    Skill,
    Termination,
)

logger = logging.getLogger(__name__)

EXCLUDED_DIRS = {
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    ".tox",
    "node_modules",
    "build",
    "dist",
    "egg-info",
    ".eggs",
}


def _is_python_file(path: Path) -> bool:
    return path.suffix == ".py"


def _should_skip_dir(name: str) -> bool:
    return name in EXCLUDED_DIRS or name.startswith(".")


def _clone_or_open(source: str) -> Path:
    """Clone a git URL or return the path for a local directory.

    Returns the path to the repository root.
    """
    parsed = urlparse(source)
    if parsed.scheme in ("http", "https") or source.startswith("git@"):
        # Git URL — clone to temp directory
        try:
            from git import Repo
        except ImportError:
            raise ImportError(
                "gitpython is required to clone remote repositories. "
                "Install with: pip install gitpython"
            )

        dest = Path(tempfile.mkdtemp(prefix="repo2skill_"))
        logger.info("Cloning %s → %s", source, dest)
        Repo.clone_from(source, str(dest), depth=1)
        return dest

    # Local path
    local = Path(source).resolve()
    if not local.exists():
        raise FileNotFoundError(f"Source not found: {source}")
    if local.is_file():
        raise ValueError(f"Expected a directory, got a file: {source}")
    return local


def _discover_python_files(root: Path) -> list[Path]:
    """Walk root to find all .py files, excluding common dirs."""
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
        for f in filenames:
            if f.endswith(".py"):
                files.append(Path(dirpath) / f)
    return sorted(files)


def _rel_path(file_path: Path, root: Path) -> str:
    """Return file path relative to root as a string."""
    try:
        return str(file_path.relative_to(root))
    except ValueError:
        return str(file_path)


def _module_from_rel(rel: str) -> str:
    """Convert a relative file path to a dotted module name."""
    s = rel.replace("/", ".").replace("\\", ".")
    if s.endswith(".py"):
        s = s[:-3]
    if s.endswith(".__init__"):
        s = s[:-9]
    return s


# ---------------------------------------------------------------------------
# AST extraction helpers
# ---------------------------------------------------------------------------


class _FuncInfo:
    """Internal struct for raw function info extracted from AST."""

    def __init__(self):
        self.name: str = ""
        self.module: str = ""
        self.file: str = ""
        self.qualname: str = ""
        self.args: list[str] = []
        self.decorators: list[str] = []
        self.docstring: str = ""
        self.return_type: str = ""
        self.is_async: bool = False
        self.is_method: bool = False
        self.class_name: str = ""
        self.has_main_block: bool = False
        self.ast_node_count: int = 0


def _extract_docstring(node: ast.AST) -> str:
    if (
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    ):
        return node.body[0].value.value.strip()
    return ""


def _count_ast_nodes(node: ast.AST) -> int:
    count = 0
    for _ in ast.walk(node):
        count += 1
    return count


def _get_type_str(node: ast.expr | None) -> str:
    """Convert an AST annotation node to a string representation."""
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant):
        return str(node.value)
    if isinstance(node, ast.Subscript):
        base = _get_type_str(node.value)
        return base
    if isinstance(node, ast.BinOp):
        left = _get_type_str(node.left)
        if isinstance(node.op, ast.BitOr):
            return left
        return ""
    return ast.unparse(node) if hasattr(ast, "unparse") else ""


def _parse_imports(tree: ast.AST) -> dict[str, set[str]]:
    """Extract imports from an AST module.

    Returns:
        dict with keys 'internal' (within-repo) and 'external' (third-party/stdlib)
        mapping to sets of module names.
    """
    internal: set[str] = set()
    external: set[str] = set()
    stdlib_modules = _stdlib_top_level()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in stdlib_modules:
                    continue
                external.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            top = node.module.split(".")[0]
            if top in stdlib_modules:
                continue
            # Relative imports are internal
            if node.level > 0:
                internal.add(node.module)
            else:
                external.add(node.module)

    return {"internal": internal, "external": external}


_STDLIB_CACHE: set[str] | None = None


def _stdlib_top_level() -> set[str]:
    """Return a set of stdlib top-level module names (cached)."""
    global _STDLIB_CACHE
    if _STDLIB_CACHE is not None:
        return _STDLIB_CACHE
    # Standard library top-level modules in Python 3.11+
    _STDLIB_CACHE = {
        "abc",
        "aifc",
        "argparse",
        "array",
        "ast",
        "asynchat",
        "asyncio",
        "asyncore",
        "atexit",
        "audioop",
        "base64",
        "bdb",
        "binascii",
        "binhex",
        "bisect",
        "builtins",
        "bz2",
        "calendar",
        "cgi",
        "cgitb",
        "chunk",
        "cmath",
        "cmd",
        "code",
        "codecs",
        "codeop",
        "collections",
        "colorsys",
        "compileall",
        "concurrent",
        "configparser",
        "contextlib",
        "contextvars",
        "copy",
        "copyreg",
        "cProfile",
        "crypt",
        "csv",
        "ctypes",
        "curses",
        "dataclasses",
        "datetime",
        "dbm",
        "decimal",
        "difflib",
        "dis",
        "distutils",
        "doctest",
        "email",
        "encodings",
        "enum",
        "errno",
        "faulthandler",
        "fcntl",
        "filecmp",
        "fileinput",
        "fnmatch",
        "fractions",
        "ftplib",
        "functools",
        "gc",
        "getopt",
        "getpass",
        "gettext",
        "glob",
        "graphlib",
        "grp",
        "gzip",
        "hashlib",
        "heapq",
        "hmac",
        "html",
        "http",
        "idlelib",
        "imaplib",
        "imghdr",
        "imp",
        "importlib",
        "inspect",
        "io",
        "ipaddress",
        "itertools",
        "json",
        "keyword",
        "lib2to3",
        "linecache",
        "locale",
        "logging",
        "lzma",
        "mailbox",
        "mailcap",
        "marshal",
        "math",
        "mimetypes",
        "mmap",
        "modulefinder",
        "multiprocessing",
        "netrc",
        "nis",
        "nntplib",
        "numbers",
        "operator",
        "optparse",
        "os",
        "ossaudiodev",
        "pathlib",
        "pdb",
        "pickle",
        "pickletools",
        "pipes",
        "pkgutil",
        "platform",
        "plistlib",
        "poplib",
        "posix",
        "pprint",
        "profile",
        "pstats",
        "pty",
        "pwd",
        "py_compile",
        "pyclbr",
        "pydoc",
        "queue",
        "quopri",
        "random",
        "re",
        "readline",
        "reprlib",
        "resource",
        "rlcompleter",
        "runpy",
        "sched",
        "secrets",
        "select",
        "selectors",
        "shelve",
        "shlex",
        "shutil",
        "signal",
        "site",
        "smtpd",
        "smtplib",
        "sndhdr",
        "socket",
        "socketserver",
        "sqlite3",
        "ssl",
        "stat",
        "statistics",
        "string",
        "stringprep",
        "struct",
        "subprocess",
        "sunau",
        "symtable",
        "sys",
        "sysconfig",
        "syslog",
        "tabnanny",
        "tarfile",
        "telnetlib",
        "tempfile",
        "termios",
        "test",
        "textwrap",
        "threading",
        "time",
        "timeit",
        "tkinter",
        "token",
        "tokenize",
        "tomllib",
        "trace",
        "traceback",
        "tracemalloc",
        "tty",
        "turtle",
        "turtledemo",
        "types",
        "typing",
        "unicodedata",
        "unittest",
        "urllib",
        "uu",
        "uuid",
        "venv",
        "warnings",
        "wave",
        "weakref",
        "webbrowser",
        "winreg",
        "winsound",
        "wsgiref",
        "xdrlib",
        "xml",
        "xmlrpc",
        "zipapp",
        "zipfile",
        "zipimport",
        "zlib",
        "zoneinfo",
    }
    return _STDLIB_CACHE


def _parse_file(file_path: Path, root: Path) -> tuple[list[_FuncInfo], dict[str, set[str]]]:
    """Parse a single Python file, returning extracted functions and imports."""
    try:
        source = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        logger.warning("Skipping %s: %s", file_path, e)
        return [], {"internal": set(), "external": set()}

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as e:
        logger.warning("Syntax error in %s: %s", file_path, e)
        return [], {"internal": set(), "external": set()}

    rel = _rel_path(file_path, root)
    module = _module_from_rel(rel)
    imports = _parse_imports(tree)
    funcs: list[_FuncInfo] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fi = _extract_func_info(node, module, rel)
            funcs.append(fi)
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    fi = _extract_func_info(item, module, rel)
                    fi.is_method = True
                    fi.class_name = node.name
                    fi.qualname = f"{module}.{node.name}.{fi.name}"
                    funcs.append(fi)

    # Detect if __name__ == "__main__" block exists
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_main_check(node.test):
            # Mark the last function before this check (if any) as main entry
            for fi in funcs:
                fi.has_main_block = True

    return funcs, imports


def _extract_func_info(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef, module: str, rel_path: str
) -> _FuncInfo:
    fi = _FuncInfo()
    fi.name = func_node.name
    fi.module = module
    fi.file = rel_path
    fi.qualname = f"{module}.{func_node.name}"
    fi.is_async = isinstance(func_node, ast.AsyncFunctionDef)
    fi.docstring = _extract_docstring(func_node)
    fi.return_type = _get_type_str(func_node.returns)
    fi.ast_node_count = _count_ast_nodes(func_node)

    for arg in func_node.args.args:
        fi.args.append(arg.arg)
        # Annotate type hints
        if arg.annotation:
            t = _get_type_str(arg.annotation)
            if t:
                fi.args[-1] = f"{arg.arg}: {t}"

    for decorator in func_node.decorator_list:
        if isinstance(decorator, ast.Name):
            fi.decorators.append(decorator.id)
        elif isinstance(decorator, ast.Attribute):
            fi.decorators.append(ast.unparse(decorator) if hasattr(ast, "unparse") else decorator.attr)
        elif isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Name):
                fi.decorators.append(decorator.func.id)
            elif isinstance(decorator.func, ast.Attribute):
                fi.decorators.append(
                    ast.unparse(decorator.func) if hasattr(ast, "unparse") else decorator.func.attr
                )

    return fi


def _is_main_check(test: ast.expr) -> bool:
    """Check if an AST expression matches `__name__ == "__main__"`."""
    if not isinstance(test, ast.Compare):
        return False
    if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
        return False
    left = test.left
    comparator = test.comparators[0] if test.comparators else None
    if (
        isinstance(left, ast.Name)
        and left.id == "__name__"
        and isinstance(comparator, ast.Constant)
        and comparator.value == "__main__"
    ):
        return True
    return False


# ---------------------------------------------------------------------------
# Four-tuple pre-annotation heuristics (P1-T4)
# ---------------------------------------------------------------------------


def _prefill_conditions(fi: _FuncInfo, imports: dict[str, set[str]]) -> Conditions:
    """Heuristically fill Conditions from function info."""
    c = Conditions()

    # Trigger: first line of docstring
    if fi.docstring:
        c.trigger = fi.docstring.splitlines()[0].strip()

    # Preconditions: inferred from dependencies (deduplicated by top-level package)
    seen_pkgs = set()
    for ext in imports.get("external", set()):
        pkg = ext.split(".")[0]
        if pkg not in seen_pkgs:
            seen_pkgs.add(pkg)
            c.preconditions.append(f"{pkg} installed")

    # File patterns: from args with Path type hints
    for arg in fi.args:
        if "path" in arg.lower() or "file" in arg.lower() or "dir" in arg.lower():
            if "str" in arg:
                c.file_patterns.append("*.py")

    # CLI entry decorators
    cli_decorators = {"click", "typer", "app", "cli", "command"}
    for dec in fi.decorators:
        if dec.lower() in cli_decorators or dec.lower().endswith("command"):
            if not c.trigger:
                c.trigger = f"CLI invocation: {fi.qualname}"
            break

    return c


def _prefill_policy(fi: _FuncInfo, imports: dict[str, set[str]]) -> Policy:
    """Heuristically fill Policy from function info."""
    p = Policy()

    # Type
    cli_decorators = {"click", "typer", "app", "cli", "command"}
    is_cli = any(d.lower() in cli_decorators or d.lower().endswith("command") for d in fi.decorators)
    if is_cli or fi.has_main_block:
        p.type = "script"
    else:
        p.type = "function"

    p.entry = fi.qualname

    # Steps: from docstring "Usage" or numbered steps
    if fi.docstring:
        p.steps = _extract_steps_from_docstring(fi.docstring)
        if not p.steps:
            p.steps = [fi.docstring.splitlines()[0].strip()]

    # Dependencies
    for ext in sorted(imports.get("external", set())):
        pkg = ext.split(".")[0]
        p.dependencies.append(pkg)
    # De-duplicate while preserving order
    seen = set()
    p.dependencies = [d for d in p.dependencies if not (d in seen or seen.add(d))]

    return p


def _extract_steps_from_docstring(docstring: str) -> list[str]:
    """Extract steps from docstring sections like Usage, Steps, or numbered items."""
    steps: list[str] = []
    # Look for "Usage:" or "Steps:" section
    in_section = False
    for line in docstring.splitlines():
        stripped = line.strip()
        if re.match(r"^(Usage|Steps|Workflow|Process)\s*:?", stripped, re.IGNORECASE):
            in_section = True
            continue
        if in_section:
            if stripped and (stripped[0].isdigit() or stripped.startswith("-")):
                steps.append(re.sub(r"^\d+[.)]\s*|^[-*]\s*", "", stripped))
            elif stripped:
                steps.append(stripped)

    if not steps:
        # Fallback: take first meaningful sentence as the step
        first = docstring.splitlines()[0].strip()
        if first:
            steps.append(first)

    return steps[:10]  # cap at 10 steps


def _prefill_termination(fi: _FuncInfo) -> Termination:
    """Heuristically fill Termination from return type and docstring."""
    t = Termination()

    if fi.return_type:
        t.success = f"Returns {fi.return_type}"
        t.output_schema = {"type": fi.return_type}
    else:
        t.success = f"Function {fi.name} completes successfully"

    # Try to extract Returns/Raises from docstring
    if fi.docstring:
        for line in fi.docstring.splitlines():
            m = re.match(r"^\s*(Returns?|Yields?)\s*:\s*(.*)", line, re.IGNORECASE)
            if m:
                t.success = m.group(2).strip()
                break

    return t


def _prefill_interface(fi: _FuncInfo) -> Interface:
    """Heuristically fill Interface from function signature."""
    iface = Interface()

    for arg in fi.args:
        if ": " in arg:
            name, typ = arg.split(": ", 1)
            iface.params[name] = typ
        else:
            iface.params[arg] = ""

    # Heuristic: infer allowed_tools from import patterns
    # subprocess/commands → Bash; file I/O → Read/Write
    if fi.has_main_block:
        tools = set()
        # Check function args for file-related names
        arg_str = " ".join(fi.args).lower()
        if any(kw in arg_str for kw in ("path", "file", "dir", "read", "write")):
            tools.update(["Read", "Write"])
        if tools:
            iface.allowed_tools = sorted(tools)

    return iface


_EXEC_IMPORTS = {"subprocess", "os", "commands"}
_NETWORK_IMPORTS = {"socket", "requests", "urllib", "http.client", "httpx"}


def _enrich_allowed_tools(skill: Skill, combined_imports: dict[str, set[str]]) -> None:
    """Enrich allowed_tools based on module-level import patterns."""
    tools = set(skill.interface.allowed_tools)
    external = combined_imports.get("external", set())

    for imp in external:
        top = imp.split(".")[0]
        if top in _EXEC_IMPORTS:
            tools.add("Bash")
        if top in _NETWORK_IMPORTS:
            tools.add("Bash")

    if tools:
        skill.interface.allowed_tools = sorted(tools)


# ---------------------------------------------------------------------------
# Dependency graph builder
# ---------------------------------------------------------------------------


def _build_dependency_graph(
    all_imports: dict[str, dict[str, set[str]]], modules: set[str]
) -> dict:
    """Build a dependency graph from per-file import data.

    Returns a dict with 'nodes' (list of module names) and
    'edges' (list of {source, target, type} dicts).
    """
    nodes = sorted(modules)
    edges: list[dict] = []

    for file_path, imports in all_imports.items():
        mod = _module_from_rel(file_path)
        for internal_mod in imports.get("internal", set()):
            edges.append({"source": mod, "target": internal_mod, "type": "internal"})
        for ext_mod in imports.get("external", set()):
            edges.append({"source": mod, "target": ext_mod, "type": "external"})

    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# README extraction
# ---------------------------------------------------------------------------


def _read_readme(root: Path) -> str:
    """Read README.md content if present."""
    for name in ("README.md", "readme.md", "README.rst", "README"):
        p = root / name
        if p.is_file():
            try:
                return p.read_text(encoding="utf-8")[:4000]
            except OSError:
                return ""
    return ""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def analyze_repo(source: str) -> AnalysisResult:
    """Analyze a repository and produce an AnalysisResult with four-tuple annotations.

    Args:
        source: A GitHub URL, git URL, or local filesystem path.

    Returns:
        AnalysisResult with extracted skills and dependency graph.
    """
    root = _clone_or_open(source)
    repo_name = root.name or source

    logger.info("Analyzing repo: %s", repo_name)

    # Discover Python files
    py_files = _discover_python_files(root)
    logger.info("Found %d Python files", len(py_files))

    if not py_files:
        return AnalysisResult(repo=repo_name, skills=[], dependency_graph={})

    # Parse each file
    all_funcs: list[_FuncInfo] = []
    all_imports: dict[str, dict[str, set[str]]] = {}
    modules: set[str] = set()

    for pf in py_files:
        funcs, imports = _parse_file(pf, root)
        all_funcs.extend(funcs)
        rel = _rel_path(pf, root)
        all_imports[rel] = imports
        mod = _module_from_rel(rel)
        modules.add(mod)

    logger.info("Extracted %d functions across %d modules", len(all_funcs), len(modules))

    # Build dependency graph
    dep_graph = _build_dependency_graph(all_imports, modules)

    # Group functions into candidate skills (module-level grouping)
    funcs_by_module: dict[str, list[_FuncInfo]] = {}
    for fi in all_funcs:
        funcs_by_module.setdefault(fi.module, []).append(fi)

    # Pre-fill four-tuple for each function and create Skill objects
    skills: list[Skill] = []
    for i, (mod, funcs) in enumerate(sorted(funcs_by_module.items()), start=1):
        # Combine imports across all files in this module
        combined_imports: dict[str, set[str]] = {"internal": set(), "external": set()}
        for rel, imps in all_imports.items():
            mod_from_rel = _module_from_rel(rel)
            if mod_from_rel == mod or mod_from_rel.startswith(mod + "."):
                combined_imports["internal"].update(imps.get("internal", set()))
                combined_imports["external"].update(imps.get("external", set()))

        # Use the first significant function as the primary
        primary = funcs[0] if funcs else None
        if primary is None:
            continue

        skill = Skill(
            id=f"sk{i}",
            name=_derive_skill_name(mod, primary),
            description=primary.docstring.splitlines()[0] if primary.docstring else f"Module {mod}",
            conditions=_prefill_conditions(primary, combined_imports),
            policy=_prefill_policy(primary, combined_imports),
            termination=_prefill_termination(primary),
            interface=_prefill_interface(primary),
        )

        # Add all related functions as part of the policy steps
        for fi in funcs:
            if fi.qualname != primary.qualname:
                skill.policy.steps.append(f"Use {fi.qualname}()")

        # Enrich allowed_tools from import patterns
        _enrich_allowed_tools(skill, combined_imports)

        skills.append(skill)

    logger.info("Generated %d candidate skills", len(skills))

    # Read readme
    readme_summary = _read_readme(root)

    return AnalysisResult(
        repo=repo_name,
        skills=skills,
        dependency_graph=dep_graph,
        readme_summary=readme_summary,
    )


def _derive_skill_name(module: str, fi: _FuncInfo | None) -> str:
    """Derive a human-readable skill name from module and function info."""
    # Convert module name to title case
    parts = module.split(".")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    name = " ".join(p.replace("_", " ").title() for p in parts if p)
    if fi and fi.name not in ("__init__", "main", "run"):
        name = f"{name} - {fi.name}"
    return name
