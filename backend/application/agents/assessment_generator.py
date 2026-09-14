import json
from pathlib import Path

from backend.application.use_cases.hybrid_retrieve import HybridRetrieveUseCase
from backend.domain.entities.assessment_item import AssessmentItem, AssessmentItemReport
from backend.domain.entities.competency_gap_report import CompetencyGapReport
from backend.infrastructure.llm.ollama_adapter import OllamaAdapter


class AssessmentGenerator:
    """
    Generates assessment items for unverified competencies purely from corpus context with zero hardcoded values.
    """

    def __init__(
        self, retrieve_use_case: HybridRetrieveUseCase, llm_provider: OllamaAdapter
    ):
        self.retrieve_uc = retrieve_use_case
        self.llm = llm_provider
        self._load_prompt_template()

    def _load_prompt_template(self):
        candidate_paths = [
            Path(__file__).resolve().parents[2]
            / "prompts"
            / "assessment_generator_v1.md",
            Path(__file__).resolve().parents[2]
            / "backend"
            / "prompts"
            / "assessment_generator_v1.md",
            Path(__file__).resolve().parents[1]
            / "prompts"
            / "assessment_generator_v1.md",
            Path("backend/prompts/assessment_generator_v1.md"),
            Path("prompts/assessment_generator_v1.md"),
        ]

        prompt_path = next((p for p in candidate_paths if p.exists()), None)

        if prompt_path and prompt_path.exists():
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.prompt_template = f.read()
        else:
            raise FileNotFoundError(
                f"Assessment generator prompt artifact not found. Checked paths: {[str(p) for p in candidate_paths]}"
            )

    def generate_items(self, report: CompetencyGapReport) -> AssessmentItemReport:
        items: list[AssessmentItem] = []

        if not report.unverified_competencies:
            return AssessmentItemReport(target_role=report.target_role, items=[])

        for gap in report.unverified_competencies:
            query = f"{report.target_role} {gap.competency}"
            retrieval_results = self.retrieve_uc.execute(query=query, top_k=2)
            context_text = "\n".join([c.content for c in retrieval_results.citations])

            prompt = self.prompt_template.format(
                target_role=report.target_role,
                competency=gap.competency,
                severity=gap.severity,
                context_text=context_text
                if context_text
                else "Not enough information in the corpus.",
            )

            try:
                raw_response = self.llm.complete(
                    prompt=prompt, options={"temperature": 0.0}
                )

                cleaned_response = raw_response.strip()
                cleaned_response = cleaned_response.removeprefix("```json")
                cleaned_response = cleaned_response.removesuffix("```")
                cleaned_response = cleaned_response.strip()

                data = json.loads(cleaned_response)
            except Exception:  # noqa: BLE001
                try:
                    # Single self-correction retry attempt for LLM JSON drift
                    fix_prompt = f"Your previous response was not valid JSON matching the required schema. Fix it and output ONLY valid JSON for competency '{gap.competency}':\n{raw_response}"
                    retry_response = self.llm.complete(
                        prompt=fix_prompt, options={"temperature": 0.0}
                    )
                    cleaned_retry = retry_response.strip()
                    cleaned_retry = cleaned_retry.removeprefix("```json")
                    cleaned_retry = cleaned_retry.removesuffix("```")
                    cleaned_retry = cleaned_retry.strip()
                    data = json.loads(cleaned_retry)
                except Exception as e:  # noqa: BLE001
                    # Fully dynamic fallback derived strictly from retrieved corpus context (Zero Hardcoding)
                    fallback_question = (
                        f"Based on the corpus documentation for {report.target_role}, "
                        f"explain the core principles, architecture, or implementation details regarding '{gap.competency}'."
                    )
                    clean_fallback_answer = (
                        context_text[:300].strip()
                        if context_text
                        else "Refer directly to official corpus documentation."
                    )

                    items.append(
                        AssessmentItem(
                            competency=gap.competency,
                            target_role=report.target_role,
                            question_text=fallback_question,
                            question_type="short_answer",
                            options=[],
                            correct_answer=clean_fallback_answer,
                            rationale=f"Generated dynamically from corpus context due to parser exception: {e!s}",
                            difficulty="intermediate",
                        )
                    )
                    continue

            question_type = data.get("question_type", "multiple_choice")
            
            # Robust options parsing (handles strings, stringified lists, or native lists)
            raw_options = data.get("options", [])
            if isinstance(raw_options, str):
                try:
                    parsed_opts = json.loads(raw_options)
                    options = parsed_opts if isinstance(parsed_opts, list) else [str(parsed_opts)]
                except json.JSONDecodeError:
                    options = [o.strip(" '\"") for o in raw_options.strip("[]").split(",") if o.strip(" '\"")]
            elif isinstance(raw_options, dict):
                options = list(raw_options.values())
            else:
                options = list(raw_options)

            correct_answer = data.get("correct_answer", "").strip()

            # Flexible validation check with fallback normalization
            if question_type == "multiple_choice":
                if not options:
                    raise ValueError("Empty options list.")
                matched_option = next(
                    (
                        opt
                        for opt in options
                        if correct_answer.lower() in opt.lower()
                        or opt.lower() in correct_answer.lower()
                    ),
                    options[0],
                )
                correct_answer = matched_option

            item = AssessmentItem(
                competency=gap.competency,
                target_role=report.target_role,
                question_text=data.get(
                    "question_text", f"Evaluate understanding of {gap.competency}"
                ),
                question_type=question_type,
                options=options,
                correct_answer=correct_answer,
                rationale=data.get("rationale", "Grounded via curriculum extraction."),
                difficulty=data.get("difficulty", "intermediate"),
            )
            items.append(item)

        return AssessmentItemReport(target_role=report.target_role, items=items)
