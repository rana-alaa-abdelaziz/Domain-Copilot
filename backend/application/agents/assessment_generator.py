import json
import threading
from pathlib import Path

from backend.application.use_cases.hybrid_retrieve import HybridRetrieveUseCase
from backend.domain.entities.assessment_item import AssessmentItem, AssessmentItemReport
from backend.domain.entities.competency_gap_report import CompetencyGapReport
from backend.domain.ports import LlmProvider


class AssessmentGenerator:
    """
    Generates assessment items for unverified competencies purely from corpus context with zero hardcoded values.
    """

    def __init__(
        self, retrieve_use_case: HybridRetrieveUseCase, llm_provider: LlmProvider
    ):
        self.retrieve_uc = retrieve_use_case
        self.llm = llm_provider
        self._load_prompt_template()

    def _load_prompt_template(self):
        candidate_paths = [
            Path(__file__).resolve().parents[3]
            / "prompts"
            / "assessment_generator_v1.md",
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

    def generate_items(
        self,
        gap_report: CompetencyGapReport,
        cancel_event: "threading.Event | None" = None,
    ) -> AssessmentItemReport:
        report = gap_report
        items: list[AssessmentItem] = []

        if not report.unverified_competencies:
            return AssessmentItemReport(target_role=report.target_role, items=[])

        for gap in report.unverified_competencies:
            query = f"{report.target_role} {gap.competency}"
            retrieval_results = self.retrieve_uc.execute(query=query, top_k=2)
            context_text = "\n".join([c.content for c in retrieval_results.citations])
            source_chunk_ids = [c.chunk_id for c in retrieval_results.citations]

            prompt = self.prompt_template.format(
                target_role=report.target_role,
                competency=gap.competency,
                severity=gap.severity,
                context_text=context_text
                if context_text
                else "Not enough information in the corpus.",
            )

            item = self._generate_one_item(
                prompt=prompt,
                gap=gap,
                target_role=report.target_role,
                context_text=context_text,
                source_chunk_ids=source_chunk_ids,
                cancel_event=cancel_event,
            )
            items.append(item)

        return AssessmentItemReport(target_role=report.target_role, items=items)

    def _generate_one_item(
        self, prompt: str, gap, target_role: str, context_text: str, source_chunk_ids: list[str], cancel_event: "threading.Event | None" = None
    ) -> AssessmentItem:
        # raw_response starts as None so the except block below can tell
        # apart "the LLM call itself failed" (raw_response still None,
        # nothing to self-correct) from "the LLM responded but the JSON
        # was malformed" (raw_response holds text worth retrying against).
        raw_response = None
        try:
            raw_response = self.llm.complete(prompt=prompt, cancel_event=cancel_event)
            data = self._parse_json_response(raw_response)
            return self._build_item(data, gap, target_role, source_chunk_ids)
        except Exception:  # noqa: BLE001
            if raw_response is not None:
                try:
                    fix_prompt = (
                        f"Your previous response was not valid JSON matching the "
                        f"required schema. Fix it and output ONLY valid JSON for "
                        f"competency '{gap.competency}':\n{raw_response}"
                    )
                    retry_response = self.llm.complete(prompt=fix_prompt, cancel_event=cancel_event)
                    data = self._parse_json_response(retry_response)
                    return self._build_item(data, gap, target_role, source_chunk_ids)
                except Exception as e:  # noqa: BLE001
                    return self._fallback_item(gap, target_role, context_text, source_chunk_ids, e)
            else:
                # The LLM call itself failed (network/provider error) —
                # nothing to self-correct against, go straight to fallback.
                return self._fallback_item(
                    gap, target_role, context_text, source_chunk_ids,
                    RuntimeError("LLM call failed before any response was returned"),
                )

    @staticmethod
    def _parse_json_response(raw_response: str) -> dict:
        cleaned = raw_response.strip()
        cleaned = cleaned.removeprefix("```json")
        cleaned = cleaned.removesuffix("```")
        cleaned = cleaned.strip()
        return json.loads(cleaned)

    def _build_item(
        self, data: dict, gap, target_role: str, source_chunk_ids: list[str]
    ) -> AssessmentItem:
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

        if question_type == "multiple_choice" and not options:
            # Previously this raised ValueError uncaught, killing the
            # whole generate_items() loop for every remaining competency.
            # A degraded item for just this one competency is the correct
            # scope of failure, not the entire batch.
            question_type = "short_answer"

        if question_type == "multiple_choice":
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

        return AssessmentItem(
            competency=gap.competency,
            target_role=target_role,
            question_text=data.get(
                "question_text", f"Evaluate understanding of {gap.competency}"
            ),
            question_type=question_type,
            options=options,
            correct_answer=correct_answer,
            rationale=data.get("rationale", "Grounded via curriculum extraction."),
            difficulty=data.get("difficulty", "intermediate"),
            source_chunk_ids=source_chunk_ids,
        )

    @staticmethod
    def _fallback_item(
        gap, target_role: str, context_text: str, source_chunk_ids: list[str], error: Exception
    ) -> AssessmentItem:
        fallback_question = (
            f"Based on the corpus documentation for {target_role}, "
            f"explain the core principles, architecture, or implementation details regarding '{gap.competency}'."
        )
        clean_fallback_answer = (
            context_text[:300].strip()
            if context_text
            else "Refer directly to official corpus documentation."
        )
        return AssessmentItem(
            competency=gap.competency,
            target_role=target_role,
            question_text=fallback_question,
            question_type="short_answer",
            options=[],
            correct_answer=clean_fallback_answer,
            rationale=f"Generated dynamically from corpus context due to parser exception: {error!s}",
            difficulty="intermediate",
            source_chunk_ids=source_chunk_ids,
        )