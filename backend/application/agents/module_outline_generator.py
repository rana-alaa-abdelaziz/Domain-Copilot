import json
from pathlib import Path

from backend.application.use_cases.hybrid_retrieve import HybridRetrieveUseCase
from backend.domain.entities.competency_gap_report import CompetencyGapReport
from backend.domain.entities.module_outline import LearningModule, ModuleOutlineReport
from backend.domain.ports import LlmProvider


class ModuleOutlineGenerator:
    """
    Groups unverified competency gaps into a structured learning module outline.
    """

    def __init__(
        self, retrieve_use_case: HybridRetrieveUseCase, llm_provider: LlmProvider
    ):
        self.retrieve_uc = retrieve_use_case
        self.llm = llm_provider
        self._load_prompt_template()

    def _load_prompt_template(self):
        candidate_paths = [
            Path(__file__).resolve().parents[3] / "prompts" / "module_outline_v1.md",
            Path(__file__).resolve().parents[2] / "prompts" / "module_outline_v1.md",
            Path(__file__).resolve().parents[2]
            / "backend"
            / "prompts"
            / "module_outline_v1.md",
            Path(__file__).resolve().parents[1] / "prompts" / "module_outline_v1.md",
            Path("backend/prompts/module_outline_v1.md"),
            Path("prompts/module_outline_v1.md"),
        ]

        prompt_path = next((p for p in candidate_paths if p.exists()), None)

        if prompt_path and prompt_path.exists():
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.prompt_template = f.read()
        else:
            raise FileNotFoundError(
                f"Module outline prompt artifact not found. Checked paths: {[str(p) for p in candidate_paths]}"
            )

    def generate_outline(self, gap_report: CompetencyGapReport) -> ModuleOutlineReport:
        if not gap_report.unverified_competencies:
            return ModuleOutlineReport(target_role=gap_report.target_role, modules=[])

        gaps_data = [
            {"competency": g.competency, "severity": g.severity}
            for g in gap_report.unverified_competencies
        ]

        # Use safe string replacement to avoid any Python .format() brace collision with JSON schemas
        prompt = self.prompt_template.replace("{target_role}", gap_report.target_role)
        prompt = prompt.replace("{gaps_json}", json.dumps(gaps_data, indent=2))

        try:
            raw_response = self.llm.complete(prompt=prompt)
            cleaned = (
                raw_response.strip().replace("```json", "").replace("```", "").strip()
            )
            data = json.loads(cleaned)

            modules = [
                LearningModule(
                    module_title=m.get("module_title", "Technical Module"),
                    objective=m.get("objective", "Master core competencies"),
                    target_competencies=m.get("target_competencies", []),
                    key_topics=m.get("key_topics", []),
                )
                for m in data.get("modules", [])
            ]
            return ModuleOutlineReport(
                target_role=gap_report.target_role, modules=modules
            )
        except json.JSONDecodeError:
            # Dynamic fallback mapping each unverified competency directly to its own module structure
            modules = [
                LearningModule(
                    module_title=f"Module on {gap.competency}",
                    objective=f"Understand and implement {gap.competency}",
                    target_competencies=[gap.competency],
                    key_topics=[gap.competency],
                )
                for gap in gap_report.unverified_competencies
            ]
            return ModuleOutlineReport(
                target_role=gap_report.target_role, modules=modules
            )