"""
Domain entity representing a structured Competency Gap Report.
Zero dependencies on external libraries or frameworks (Clean Architecture).
"""
from dataclasses import dataclass, field
from typing import Literal

from backend.domain.entities.assessment_item import AssessmentItemReport

CoverageSource = Literal["corpus_citation", "model_inference", "unverified"]
Severity = Literal["critical", "moderate", "minor"]


@dataclass
class CompetencyGap:
    competency: str
    required_by_chunk_ids: list[str] = field(default_factory=list)
    coverage_source: CoverageSource = "unverified"
    severity: Severity = "moderate"
    coverage_chunk_ids: list[str] = field(default_factory=list)
    matched_user_subject: str | None = None

    def __post_init__(self):
        if not self.competency or not self.competency.strip():
            raise ValueError("Competency name cannot be empty.")
        if self.coverage_source not in {"corpus_citation", "model_inference", "unverified"}:
            raise ValueError(f"Invalid coverage_source: {self.coverage_source}")
        if self.severity not in {"critical", "moderate", "minor"}:
            raise ValueError(f"Invalid severity: {self.severity}")


@dataclass
class CompetencyGapReport:
    target_role: str
    user_reported_subjects: list[str] = field(default_factory=list)
    gaps: list[CompetencyGap] = field(default_factory=list)
    assessment_report: AssessmentItemReport | None = None

    @property
    def critical_gaps(self) -> list[CompetencyGap]:
        return [g for g in self.gaps if g.severity == "critical"]

    @property
    def covered_competencies(self) -> list[CompetencyGap]:
        return [g for g in self.gaps if g.coverage_source in {"corpus_citation", "model_inference"}]

    @property
    def unverified_competencies(self) -> list[CompetencyGap]:
        return [g for g in self.gaps if g.coverage_source == "unverified"]