# Extractor: Five-Step Extraction

The structurer (`structure.py`) produces **raw function data** in `analysis.json` — no filtering, no quality judgments, no tool inference. The rule-based `extract.py` produces `candidates.json` with baseline scores as **hints only**.

**Your job as Extractor**: Read the raw data from `analysis.json` (all functions, dependency graph, readme summary), use `candidates.json` scores as hints, then make all quality decisions yourself.

## Step A: Read Everything

```text
Read analysis.json → all skills (full list, not just top 5)
Read candidates.json → rule-based scores (hints, not decisions)
Read readme_summary → repo-level intent and purpose
Skim dependency_graph → which modules call each other
```

## Step B: Filter

Scan every function in `analysis.json.skills[]` and skip those that aren't teachable skills:

| Skip                                                       | Why                                                                                |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Module path contains `/test/` or `/tests/`                 | Test helpers follow common patterns — not reusable skills                          |
| Entry function is `__init__`                               | Class constructors are class-bound; the class's public methods are the real skills |
| Entry function starts with `_` (private)                   | Private helpers have narrow scope — unless they're the ONLY function in the module |
| All functions in the module are `_`-prefixed               | No public interface to teach                                                       |
| Only function is `main()` and it just calls another module | Thin wrappers — teach the underlying module instead                                |

Keep everything else. You may end up with 20-50 candidates from a large repo. That's fine — you'll score and merge next.

## Step C: Merge

Merge related functions into workflow-level skills to avoid producing dozens of single-function skills:

1. **Same-module**: If multiple functions from one module form a pipeline (A calls B, B calls C in the dependency graph), merge into one `"workflow"` skill. The top-level entry function is the primary.

2. **Cross-module call chains**: If function A in module X calls function B in module Y (visible in `dependency_graph` edges), and B is the sole public function of Y, merge B into A's skill. Trace up to 3 levels.

3. **Do NOT merge**:
   - Functions from `test_*` modules (these aren't skills)
   - Functions with no callers AND no callees (leaf nodes) — unless they're CLI entries
   - Functions from entirely different subsystems (e.g., don't merge a linter with a formatter)

After merging, set the merged skill's `policy.type` to `"workflow"`.

## Step D: Score

Apply the 4 criteria to each candidate (with modifiers), then rank:

**Base criteria** (each 0.0–1.0):

| Criterion            | What to evaluate                                                                                                         |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| **Recurrence**       | How unique? Rare patterns = higher value. Check `dependency_graph` for similar structures.                               |
| **Verification**     | How well-documented? Type hints in `interface.params`, specificity of `policy.steps`, docstring in `conditions.trigger`. |
| **Non-obviousness**  | How complex? Step count, dependency breadth, precondition count. Higher complexity = more documentation value.           |
| **Generalizability** | How reusable? Parameter count (discount `self`), breadth of `conditions.file_patterns`, function vs script type.         |

**Modifiers** (apply to the criterion score):

| Condition                                                                        | Criterion        | Adj  | Reason                          |
| -------------------------------------------------------------------------------- | ---------------- | ---- | ------------------------------- |
| CLI entry (`if __name__ == "__main__"` or in `pyproject.toml [project.scripts]`) | Generalizability | +0.2 | CLI tools have clear invocation |
| High fan-in (3+ other modules reference it in `dependency_graph`)                | Non-obviousness  | +0.2 | Widely-used = infrastructure    |
| Complete docstring (Args + Returns + Raises)                                     | Verification     | +0.2 | Richer documentation            |
| `__init__` method                                                                | Generalizability | -0.2 | Constructor, not standalone     |
| Test function (module path contains `test/`)                                     | Recurrence       | -0.3 | Common test pattern             |
| Private function (`_` prefix)                                                    | Generalizability | -0.2 | Narrow reuse scope              |

Confidence: `(recurrence + verification + non_obviousness + generalizability) / 4`, ±0.1 for qualitative judgment.

## Step E: Enrich

Before presenting, improve the quality of the top 1-5 candidates:

**Name**: Use `readme_summary` for repo context. Prefer functional names like "Skill Extraction Pipeline" over "Src Repo2Skill Extractor - extract_skills".

**Description**: Combine `readme_summary` first paragraph + the entry function's purpose.

**Policy steps**: Rewrite `"Use module.func()"` references into natural language. Extract from each function's docstring first line. Drop the `"Use "` prefix.

**Dependencies**: Remove `__future__` and Python stdlib from the list. Only keep packages that require `pip install`.

**Allowed tools**: Infer from import patterns: `subprocess`/`os.system` → `Bash`, `open()`/`Path` → `Read`/`Write`, `requests`/`urllib` → network (flag for review).

## Candidate Presentation Format

```text
[skN] Skill Name (confidence: X.XX)
  Reasoning: <why this skill was selected, what makes it valuable>
  Entry: policy.entry
  Type: policy.type (workflow if merged)
  Allowed Tools: [interface.allowed_tools]
```
