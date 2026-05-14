# Enrichment Guide: Rewriting Assembled Skills

After `assemble.py` runs, the generated SKILL.md files contain **template-filled placeholder content**. Your job is to substantially rewrite each one. Read the assembled file, then edit it in-place using your Write tool.

## What to Change

Every section of the generated SKILL.md should be reviewed and improved:

**Frontmatter**:

- `description`: Replace the raw docstring line with a 1-2 sentence summary of what the skill teaches the Agent to do. Combine `readme_summary` context with the function's purpose.
- `trust-level`: Update to reflect G1 result (L1 if G1 passed, L0 otherwise).

**`# Title`**: Replace the module-path name with a functional name. Example: `"Repo2Skill Suite - detect_suite_mode"` → `"Skill Suite Detection"`.

**`## Conditions > ### Trigger`**: Rewrite as user intent. Instead of `"Determine whether the repo should be decomposed"`, write `"User asks whether a repository should be split into multiple skills instead of one large skill."`

**`## Policy > ### Steps`**: This is the most important rewrite. Replace `"Use module.func()"` references with natural language instructions. For each function in the step list, read its docstring from `analysis.json` and write what it actually DOES.

**`## Policy > ### Dependencies`**: Remove `__future__`, Python stdlib modules. Only keep packages that need `pip install`.

**`## Interface > ### Parameters`**: Prune `self` from the parameter list. Keep only user-facing parameters.

**`## Security`**: Update `Trust Level` and `G1 Passed` to reflect actual G1 scan results.

## Example: Before → After

**Before** (template output):

```markdown
---
name: Repo2Skill Suite - detect_suite_mode
description: Determine whether the repo should be decomposed into a Skill Suite.
version: 0.1.0
dependencies:
  - jinja2
  - repo2skill
allowed-tools: []
trust-level: L0
---

# Repo2Skill Suite - detect_suite_mode

## Conditions

### Trigger

Determine whether the repo should be decomposed into a Skill Suite.

## Policy

### Type

function

### Entry Point

`src.repo2skill.suite.detect_suite_mode`

### Steps

1. Determine whether the repo should be decomposed into a Skill Suite.
2. Use src.repo2skill.suite.\_estimate_combined_tokens()
3. Use src.repo2skill.suite.find_disconnected_clusters()
4. Use src.repo2skill.suite.infer_relations()
5. Use src.repo2skill.suite.validate_dag()
6. Use src.repo2skill.suite.assemble_suite()
```

**After** (Agent-enriched):

```markdown
---
name: Skill Suite Detection
description: Analyze a repository to determine if it should be decomposed into multiple interconnected skills instead of one monolithic skill.
version: 0.1.0
dependencies:
  - jinja2
allowed-tools: []
trust-level: L1
---

# Skill Suite Detection

## Conditions

### Trigger

User asks whether a repository should be split into a Skill Suite, or the Extractor detects multiple independent skill candidates.

## Policy

### Type

workflow

### Entry Point

`src.repo2skill.suite.detect_suite_mode`

### Steps

1. Check if the number of skill candidates exceeds 1 (single-skill repos don't need suites).
2. Estimate the combined token count of all candidates' Level 2 bodies. If total exceeds 4,000 tokens, a suite is needed to stay within progressive disclosure limits.
3. Find disconnected clusters in the dependency graph using BFS — independent subgraphs suggest natural skill boundaries.
4. Infer inter-skill relations from the dependency graph: `depends-on` from import edges, `bundled-with` from matching policy types and tool sets.
5. Validate that the relationship graph forms a DAG (no cycles) using DFS. Cycles indicate incorrect skill boundaries that need rework.
6. If any criterion is met, recommend suite mode and assemble the suite with DAG-validated relations.
```

## Token Budget

The enriched skill must still respect progressive disclosure:

- **Level 1 frontmatter**: 30–100 tokens
- **Level 2 body**: 200–5,000 tokens

If your enrichment pushes body beyond 5,000 tokens, trim the less important detail or split into a Skill Suite instead.
