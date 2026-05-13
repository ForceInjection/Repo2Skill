# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Repo2Skill is an Agent Skill that teaches an Agent how to decompose any Git repository and produce a verified, standards-compliant Agent Skill (or a Skill Suite for complex repos). It follows the Anthropic Agent Skills protocol.

**Status**: Phase 1 (core pipeline) + Phase 2 (G1/G2, Skill Suite) implemented. Phases 3–5 are design-only.

## Commands

```bash
# First-time setup
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run all tests (60 tests across smoke + phase2)
.venv/bin/python -m pytest tests/ -v

# Run a single test
.venv/bin/python -m pytest tests/phase2/test_suite.py::TestValidateDAG::test_cycle_detected -v

# Run the CLI on a repo
.venv/bin/repo2skill <path-or-url> --non-interactive -o ./output

# Run CLI with suite mode
.venv/bin/repo2skill <path-or-url> --mode suite --confidence-threshold 0.3 -o ./output

# Show all CLI flags
.venv/bin/repo2skill --help
```

No linting or type-checking is configured. No Makefile or tox exists. Just pytest.

## Architecture: Agent Skills Protocol

The project is **itself an Agent Skill**. The `repo2skill-skill/` directory is the distributable manifest that any Agent can load. The `src/repo2skill/` Python package provides deterministic scripts the Agent invokes via Bash.

**Core principle**: The Agent (Claude Code) does all LLM reasoning. Python scripts do only deterministic work. There are no API keys passed to Python files and no `llm_client.py` / `extractor_llm.py`.

```
repo2skill-skill/          ← Distributable Agent Skill
├── SKILL.md               ← Teaches the Agent the full workflow
├── skill.yaml             ← Repo2Skill's own metadata
├── scripts/               ← Thin wrappers that import from src/repo2skill/
│   ├── structure.py       ← → repo2skill.structure.analyze_repo()
│   ├── extract.py         ← → repo2skill.extractor.extract_skills_with_scores()
│   ├── assemble.py        ← → repo2skill.assemble / repo2skill.suite
│   ├── audit_g1.py        ← → repo2skill.reviewer.g1.run_g1_scan()
│   └── audit_g2.py        ← Generates review-context.md for the Agent
└── templates/ → ../../templates  (symlink)

src/repo2skill/            ← Python package
├── models.py              ← All Pydantic models (Skill, SkillCandidate, AnalysisResult,
│                             G1Report, G2Report, SuiteConfig)
├── structure.py           ← Structurer: clone, AST parse, dependency graph → analysis.json
├── extractor.py           ← Rule-based scoring (baseline); Agent refines via SKILL.md
├── assemble.py            ← Renders Jinja2 → SKILL.md + skill.yaml
├── suite.py               ← Suite detection (4 criteria), DAG validation, suite assembly
├── reviewer/
│   ├── g1.py              ← G1 deterministic static scan (17 regex/AST patterns)
│   └── g2.py              ← Not yet created (Phase 2 G2 is Agent-driven via SKILL.md)
└── cli.py                 ← typer CLI with --interactive, --mode, --force-continue, etc.
```

## Pipeline Flow

```
[source repo]
    │
    ▼
structure.py ───► analysis.json ───► Agent (Extractor)
    (deterministic)                     (reads analysis.json,
                                        applies 4 screening criteria,
                                        presents 1–5 candidates)
                                            │
                                            ▼
                                    assemble.py ───► SKILL.md + skill.yaml
                                    (deterministic)
                                            │
                                            ▼
                                    audit_g1.py ───► G1 report
                                    (deterministic)
                                            │
                                            ▼
                                    Agent (Reviewer G2)
                                    (reads skill output,
                                     checks hallucination,
                                     injection, consistency)
                                            │
                                            ▼
                                    Trust Level (L0–L2)
```

## Key Design Points

- **Four-tuple model**: `analysis.json` uses ASCII keys `conditions`/`policy`/`termination`/`interface` (matching design §2.1 symbols C/π/T/R).
- **Extractor**: The rule-based `extract_skills_with_scores()` in `extractor.py` provides baseline scoring. The Agent reads `analysis.json` and applies LLM reasoning to refine scores per `SKILL.md` instructions.
- **Suite mode (4 criteria)**: candidate count > 1 & combined tokens > 4,000; multiple entry-point types; disconnected dependency clusters (BFS); divergent `allowed-tools` sets.
- **Suite relations**: `depends-on`, `composes`, `bundled-with`, `requires-output-from`. DAG validated via DFS cycle detection (only `depends-on` + `requires-output-from` are directional).
- **Trust levels**: L0 (unverified) → L1 (G1 passed, no high-severity findings) → L2 (G2 score ≥ 0.8). L3–L4 require Phase 3 infrastructure.
- **G1 scan**: Scans Python files in the assembed skill directory. 17 patterns at high/medium/low severity. Only "high" findings block (unless `--force-continue`).
- **`skill.yaml` uses kebab-case** (`trust-level`, `allowed-tools`, `g1-passed`, `g2-score`).
- **`suite.yaml` uses `suite-id`** and relation keys `from`/`to` (matching design §4).
- **No network requests** in scripts (only `git clone` in structure.py).
- **Writing scoped** to user-specified output directory only.

## Testing

60 tests, all passing. Two test directories:

- **`tests/smoke/`** (8 tests) — Phase 1 smoke tests. Use `create_sample_repo()` helper to create tiny test repos. Must always pass.
- **`tests/phase2/`** (52 tests) — Phase 2 tests covering models, G1 scan, suite detection/DAG, CLI E2E. Use both library-level and subprocess-based CLI tests. All mock-driven; no real external API calls.

Key test helpers: `create_sample_repo()` in `tests/smoke/test_phase1.py` and `create_multi_module_repo()` in `tests/phase2/test_cli_phase2.py`.

## What's NOT Implemented Yet

- **G3/G4**: Docker sandbox + permission audit (Phase 3)
- **Multi-language**: Currently Python-only via stdlib `ast`. `tree-sitter` planned for Phase 4.
- **Dense retrieval + Cross-Encoder**: Phase 1–2 uses deterministic rules. The design §3.2 specifies `sentence-transformers` for Phase 3+.
- **`audit_g3.py` / `audit_g4.py`**: Listed in design §4 but not created.
- **`reviewer/g2.py`**: G2 review is currently Agent-driven via `SKILL.md`, not a Python module. The `audit_g2.py` wrapper generates a review context `.md` file for the Agent to consume.
