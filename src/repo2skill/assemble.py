"""Assembler: render Jinja2 templates → final skill directory.

Creates the output skill directory with SKILL.md, skill.yaml, and required
subdirectories. Validates progressive disclosure token budgets.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from repo2skill.models import Skill

logger = logging.getLogger(__name__)

# Token budget for progressive disclosure (design.md §2.4)
LEVEL1_MIN_TOKENS = 30
LEVEL1_MAX_TOKENS = 100
LEVEL2_MIN_TOKENS = 200
LEVEL2_MAX_TOKENS = 5000

TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates"


def _get_template_env() -> Environment:
    """Create a Jinja2 environment pointing to the templates directory."""
    if not TEMPLATE_DIR.is_dir():
        raise FileNotFoundError(f"Templates directory not found: {TEMPLATE_DIR}")
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=False,
        keep_trailing_newline=True,
    )


def _estimate_tokens(text: str) -> int:
    """Rough token count estimate: ~4 chars per token for English text."""
    return len(text) // 4


def assemble_skill(
    skill: Skill,
    output_dir: Path,
    source: str = "",
    version: str = "0.1.0",
    trust_level: str = "L0",
    g1_passed: bool = False,
    g2_score: float = 0.0,
    ontology_relations: list[dict] | None = None,
) -> Path:
    """Render a Skill into a standards-compliant skill directory.

    Args:
        skill: The Skill model to assemble.
        output_dir: Directory to write the skill into.
        source: Original repo source URL/path.
        version: Skill version string.
        trust_level: Trust level computed from G1/G2 results.
        g1_passed: Whether G1 scan passed.
        g2_score: G2 review aggregate score (0.0–1.0).
        ontology_relations: Per-skill relations for SkillNet (design.md §8.3).

    Returns:
        Path to the created skill directory.
    """
    env = _get_template_env()

    # Per-skill relations: [{type, target}, ...]
    rels = ontology_relations or []

    # Build template context
    ctx = {
        "name": skill.name,
        "description": skill.description or skill.conditions.trigger or skill.name,
        "version": version,
        "source": source,
        "trust_level": trust_level,
        "g1_passed": g1_passed,
        "g2_score": g2_score,
        "dependencies": skill.policy.dependencies,
        "allowed_tools": skill.interface.allowed_tools,
        "ontology_relations": rels,
        "conditions_trigger": skill.conditions.trigger or "No trigger defined",
        "preconditions": skill.conditions.preconditions,
        "file_patterns": skill.conditions.file_patterns,
        "policy_type": skill.policy.type or "function",
        "policy_entry": skill.policy.entry,
        "policy_steps": skill.policy.steps,
        "termination_success": skill.termination.success,
        "termination_schema": skill.termination.output_schema if skill.termination.output_schema else None,
        "interface_params": skill.interface.params,
    }

    # Render SKILL.md
    md_template = env.get_template("skill.md.j2")
    md_content = md_template.render(**ctx)

    # Render skill.yaml
    yaml_template = env.get_template("skill.yaml.j2")
    yaml_content = yaml_template.render(**ctx)

    # Validate progressive disclosure token budgets
    _validate_token_budgets(md_content)

    # Create output directory structure (sanitize name)
    import re
    skill_name = re.sub(r"[^a-z0-9]+", "-", skill.name.lower()).strip("-")
    skill_dir = output_dir / f"{skill_name}-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)

    # Write SKILL.md
    (skill_dir / "SKILL.md").write_text(md_content, encoding="utf-8")
    logger.info("Wrote %s/SKILL.md", skill_dir)

    # Write skill.yaml
    (skill_dir / "skill.yaml").write_text(yaml_content, encoding="utf-8")
    logger.info("Wrote %s/skill.yaml", skill_dir)

    # Create auxiliary directories (Level 3 assets)
    for subdir in ("scripts", "references", "templates", "verification"):
        (skill_dir / subdir).mkdir(exist_ok=True)

    logger.info("Assembled skill at %s", skill_dir)
    return skill_dir


def _validate_token_budgets(md_content: str) -> None:
    """Validate that SKILL.md respects progressive disclosure token budgets.

    Minimums are warnings (quality recommendation). Maximums raise ValueError
    (hard constraint per design.md §2.4).
    """
    # Split frontmatter from body
    if md_content.startswith("---"):
        parts = md_content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            body = parts[2]
        else:
            frontmatter = ""
            body = md_content
    else:
        frontmatter = ""
        body = md_content

    fm_tokens = _estimate_tokens(frontmatter)
    body_tokens = _estimate_tokens(body.strip())

    if fm_tokens > 0:
        if fm_tokens < LEVEL1_MIN_TOKENS:
            logger.warning(
                "Level 1 frontmatter is %d tokens (min %d). Add more metadata.",
                fm_tokens, LEVEL1_MIN_TOKENS,
            )
        elif fm_tokens > LEVEL1_MAX_TOKENS:
            raise ValueError(
                f"Level 1 frontmatter is {fm_tokens} tokens "
                f"(maximum {LEVEL1_MAX_TOKENS}). Trim metadata."
            )
        else:
            logger.info("Level 1 frontmatter: %d tokens (valid)", fm_tokens)

    if body_tokens < LEVEL2_MIN_TOKENS:
        logger.warning(
            "Level 2 body is %d tokens (min %d). Skill may lack sufficient instructions.",
            body_tokens, LEVEL2_MIN_TOKENS,
        )
    elif body_tokens > LEVEL2_MAX_TOKENS:
        raise ValueError(
            f"Level 2 body is {body_tokens} tokens "
            f"(maximum {LEVEL2_MAX_TOKENS}). Split into a Skill Suite."
        )
    else:
        logger.info("Level 2 body: %d tokens (valid)", body_tokens)
