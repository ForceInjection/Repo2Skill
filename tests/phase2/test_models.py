"""Tests for Phase 2 model extensions (SkillCandidate, G1Report, G2Report, SuiteConfig)."""

from repo2skill.models import (
    AnalysisResult,
    Conditions,
    G1Report,
    G2Report,
    Interface,
    Policy,
    Skill,
    SkillCandidate,
    SuiteConfig,
    Termination,
)


class TestSkillCandidate:
    def test_skill_candidate_extends_skill(self):
        skill = Skill(
            id="sk1",
            name="Test Skill",
            description="A test skill",
            conditions=Conditions(triggers=["Test trigger"]),
            policy=Policy(type="function", entry="test.main", steps=["Step 1", "Step 2"]),
            termination=Termination(success="Done"),
            interface=Interface(params={"x": "int"}, allowed_tools=["Read"]),
        )
        candidate = SkillCandidate(
            **skill.model_dump(),
            confidence=0.85,
            reasoning="Well-documented and reusable",
            scores={
                "recurrence": 0.7,
                "verification": 0.9,
                "non_obviousness": 0.6,
                "generalizability": 0.8,
            },
        )

        assert candidate.id == "sk1"
        assert candidate.confidence == 0.85
        assert "reusable" in candidate.reasoning
        assert candidate.scores["verification"] == 0.9
        assert isinstance(candidate, Skill)  # inheritance works

    def test_skill_candidate_defaults(self):
        candidate = SkillCandidate(id="sk1", name="Default Test")
        assert candidate.confidence == 0.0
        assert candidate.reasoning == ""
        assert candidate.scores == {}


class TestAnalysisResult:
    def test_readme_summary_field(self):
        result = AnalysisResult(
            repo="test-repo",
            skills=[],
            dependency_graph={},
            readme_summary="# Test\nThis is a test README.",
        )
        assert result.readme_summary.startswith("# Test")

    def test_readme_summary_default(self):
        result = AnalysisResult(repo="test-repo")
        assert result.readme_summary == ""


class TestG1Report:
    def test_g1_report_clean(self):
        report = G1Report(skill_name="test-skill", passed=True, findings=[])
        assert report.passed is True
        assert report.findings == []

    def test_g1_report_with_findings(self):
        findings = [
            {
                "pattern": r"\beval\s*\(",
                "description": "eval() call — arbitrary code execution",
                "file": "scripts/dangerous.py",
                "line": 10,
                "severity": "high",
                "snippet": "eval(user_input)",
            }
        ]
        report = G1Report(skill_name="bad-skill", passed=False, findings=findings)
        assert report.passed is False
        assert len(report.findings) == 1
        assert report.findings[0]["severity"] == "high"


class TestG2Report:
    def test_g2_report_complete(self):
        report = G2Report(
            skill_name="test-skill",
            score=0.95,
            verdict="complete",
            hallucination_check="No hallucinations found",
            injection_check="No injection risks",
            metadata_consistency="Frontmatter and skill.yaml are consistent",
            recommendations=[],
        )
        assert report.verdict == "complete"
        assert report.score >= 0.9

    def test_g2_report_questionable(self):
        report = G2Report(
            skill_name="bad-skill",
            score=0.3,
            verdict="questionable",
            hallucination_check="References non-existent function",
            injection_check="Contains manipulative language",
            metadata_consistency="Version mismatch between frontmatter and skill.yaml",
            recommendations=["Fix API references", "Remove manipulative language"],
        )
        assert report.verdict == "questionable"
        assert report.score < 0.5
        assert len(report.recommendations) == 2


class TestSuiteConfig:
    def test_suite_config(self):
        config = SuiteConfig(
            name="Test Suite",
            description="A test suite",
            skills=["sk1", "sk2"],
            relations=[
                {"source": "sk1", "target": "sk2", "type": "depends-on"},
                {"source": "sk2", "target": "sk1", "type": "composes"},
            ],
        )
        assert config.name == "Test Suite"
        assert len(config.skills) == 2
        assert len(config.relations) == 2

    def test_suite_config_defaults(self):
        config = SuiteConfig()
        assert config.name == ""
        assert config.skills == []
        assert config.relations == []
