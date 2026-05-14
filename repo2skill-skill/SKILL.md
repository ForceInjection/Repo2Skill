---
name: repo2skill
description: Decompose a Python Git repository into an Agent Skill or Skill Suite. Use when a user asks to convert, decompose, or skill-ify a Python repo URL or local path.
version: 0.2.0
allowed-tools:
  - Read
  - Write
  - Bash
  - Glob
  - Grep
trust-level: L1
---

# Repo2Skill

## Conditions

### Trigger

User asks to convert, decompose, or skill-ify a Python repository into an Agent Skill.

### Preconditions

- Python 3.11+ with repo2skill package installed (`pip install -e .`)
- Source repo is accessible (local path, git URL, or GitHub URL)

### File Patterns

- `*.py` (source code to analyze)
- `analysis.json` (intermediate artifact from Structurer)
- `candidates.json` (rule-based baseline scores from extract.py)
- `SKILL.md`, `skill.yaml`, `suite.yaml` (output artifacts)

## Policy

### Type

workflow

### Entry Point

`repo2skill-skill/SKILL.md` (this file)

### Steps

1. **Structure**: Run `scripts/structure.py <source> <output_dir>` — clones the repo, parses all Python files via AST, builds the dependency graph, pre-annotates the four-tuple for each module, and writes `analysis.json` (includes `skills[]`, `dependency_graph`, `readme_summary`).

2. **Extract (baseline)**: Run `scripts/extract.py <analysis.json> <output_dir>` — applies rule-based scoring (recurrence, verification, non-obviousness, generalizability) and writes `candidates.json` with `SkillCandidate` objects containing `confidence`, `reasoning`, and per-criterion `scores`.

3. **Extract (Agent refinement)**: Read `analysis.json` and `candidates.json`. Act as the Extractor by following the five-step procedure in `references/extractor-guide.md` — filter, merge, score, enrich — and select the top 1–5 candidates.

4. **Present candidates** to the user. In interactive mode, let the user choose which to generate. In non-interactive mode, auto-select candidates whose final confidence exceeds the threshold (default 0.5).

5. **Detect suite mode** before assembling. Apply the 4 criteria in `references/suite-mode.md`. If any criterion is met, propose suite mode and validate that inter-skill relations form a DAG.

6. **Assemble**: Run `scripts/assemble.py <analysis.json> <selected_ids> <output_dir> [--mode suite]` — renders Jinja2 templates into `SKILL.md` + `skill.yaml` (single mode) or `suite.yaml` + per-skill subdirectories (suite mode). Validates progressive disclosure token budgets. **The output at this stage is a structural starting point — the content is template-generated and needs enrichment.**

7. **Enrich (Agent rewrites)**: The assembled SKILL.md files contain template-filled content. Read each assembled SKILL.md and substantially rewrite it following `references/enrichment-guide.md`. Write the enriched content back to the same files. This is the most important step for skill quality.

8. **G1 scan**: Run `scripts/audit_g1.py <skill_dir>` — deterministic regex/AST scan for dangerous patterns (`eval`, `exec`, `subprocess`, `socket`, `os.system`, `shutil.rmtree`, Jinja2 `|safe`, etc.). If HIGH-severity findings are found, block and warn the user (unless `--force-continue`).

9. **G2 review (preparation)**: Run `scripts/audit_g2.py <skill_dir> <analysis.json>` — generates `g2_<skill>.md`, a structured review context file combining the assembled skill content with the source analysis.

10. **G2 review (Agent)**: Read the `g2_<skill>.md` context file and act as the Reviewer G2 by following `references/g2-review.md` — evaluate hallucination, prompt injection, and metadata consistency, then compute an aggregate score.

11. **Record G2 results**: Write the G2 verdict and aggregate score into the generated `skill.yaml` under `security.g2-score`. If suite mode, update each sub-skill's `skill.yaml`.

12. **Compute trust level**: Determine L0, L1, or L2 using the rules in `references/trust-levels.md`. Report the final trust level to the user.

### Dependencies

- typer, pydantic, gitpython, jinja2, pyyaml
- git (for cloning remote repos)

## Termination

### Success Criteria

A valid Agent Skill directory (or Skill Suite) is produced with:

- `SKILL.md` passing progressive disclosure token budgets (Level 1: 30–100 tokens, Level 2: 200–5,000 tokens)
- `skill.yaml` with valid kebab-case metadata
- G1 scan passed (or user explicitly overrode with `--force-continue`)
- G2 review score recorded in `skill.yaml` under `security.g2-score`
- Trust level assigned (L0, L1, or L2)

### Output Schema

```json
{
  "skill_dir": "string (path to generated skill)",
  "skill_name": "string",
  "trust_level": "L0 | L1 | L2",
  "g1_passed": "boolean",
  "g2_score": "float (0.0–1.0)",
  "candidates": ["SkillCandidate"],
  "mode": "single | suite"
}
```

## Interface

### Parameters

| Parameter              | Type                      |
| ---------------------- | ------------------------- |
| `source`               | `str` (repo URL or path)  |
| `out`                  | `Path` (output directory) |
| `mode`                 | `single \| suite \| auto` |
| `interactive`          | `bool`                    |
| `confidence_threshold` | `float` (0.0–1.0)         |
| `force_continue`       | `bool`                    |

## References

Detailed reference material lives in `references/`:

- [`references/extractor-guide.md`](references/extractor-guide.md) — Five-step extraction procedure (filter, merge, score, enrich) with scoring criteria and modifiers.
- [`references/enrichment-guide.md`](references/enrichment-guide.md) — How to rewrite template-filled SKILL.md files into high-quality skills, with a before/after example.
- [`references/g2-review.md`](references/g2-review.md) — The three-dimension semantic review (hallucination, injection, consistency) and aggregate scoring.
- [`references/trust-levels.md`](references/trust-levels.md) — L0/L1/L2 computation rules.
- [`references/suite-mode.md`](references/suite-mode.md) — When to decompose into a Skill Suite and DAG validation.

## Security

- **Trust Level**: L1 (G1 scan integrated; G2 review performed by Agent)
- **Allowed Tools**: Read, Write, Bash, Glob, Grep
- **Network Access**: Denied (no network calls in scripts; git clone is the only network operation)
- **Filesystem Scope**: `$(workspace)/*` and the user-specified output directory
