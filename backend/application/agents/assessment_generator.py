import json
import logging
import threading
from pathlib import Path

from backend.application.use_cases.hybrid_retrieve import HybridRetrieveUseCase
from backend.domain.entities.assessment_item import AssessmentItem, AssessmentItemReport, validate_item_semantics
from backend.domain.entities.competency_gap_report import CompetencyGapReport
from backend.domain.ports import LlmProvider

logger = logging.getLogger(__name__)

QUESTIONS_PER_SUBJECT = 5   # questions generated per gap subject
MAX_GAP_SUBJECTS = 5        # max subjects processed per run (cap total Ollama calls)


class AssessmentGenerator:
    """
    Generates assessment items for unverified competency gaps purely from corpus
    context, with zero hardcoded values.

    Architecture: modular, one LLM call per gap subject so that a single bad
    LLM response cannot wipe the entire assessment.
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
                f"Assessment generator prompt artifact not found. "
                f"Checked paths: {[str(p) for p in candidate_paths]}"
            )

    def generate_items(
        self,
        gap_report: CompetencyGapReport,
        cancel_event: "threading.Event | None" = None,
    ) -> AssessmentItemReport:

        # 1. Target the Gaps — select only competencies the user does NOT know
        gap_competencies = [
            c
            for c in gap_report.gaps
            if not c.matched_user_subject
            or str(c.matched_user_subject).lower() == "none"
        ]

        if not gap_competencies:
            logger.warning(
                "AssessmentGenerator: no gap competencies found in report for role '%s'.",
                gap_report.target_role,
            )
            return AssessmentItemReport(target_role=gap_report.target_role, items=[])

        # Sort by severity (critical first) then cap to MAX_GAP_SUBJECTS
        # so the highest-priority gaps are always assessed within the time budget.
        SEVERITY_ORDER = {"critical": 0, "moderate": 1, "minor": 2}
        gap_competencies.sort(key=lambda c: SEVERITY_ORDER.get(c.severity, 9))
        gap_competencies = gap_competencies[:MAX_GAP_SUBJECTS]
        logger.info(
            "AssessmentGenerator: processing %d gap(s) for role '%s' (capped at %d).",
            len(gap_competencies), gap_report.target_role, MAX_GAP_SUBJECTS,
        )

        # Master list — accumulated across all per-subject LLM calls
        all_assessment_items: list[AssessmentItem] = []

        for gap in gap_competencies:
            # Thread-safety: respect cancellation between subjects
            if cancel_event and cancel_event.is_set():
                logger.info("AssessmentGenerator: cancelled before processing '%s'.", gap.competency)
                break

            # 2. Retrieve context FIRST — Anti-Hallucination Guardrail
            retrieval_results = self.retrieve_uc.execute(query=gap.competency, top_k=5)
            if not retrieval_results.citations:
                logger.warning(
                    "AssessmentGenerator: no curriculum chunks found for gap '%s' — skipping.",
                    gap.competency,
                )
                continue

            context_text = "\n".join(cit.content for cit in retrieval_results.citations)
            chunk_ids = [cit.chunk_id for cit in retrieval_results.citations]

            # 3. Build per-subject prompt
            prompt = self.prompt_template.format(
                target_subject=gap.competency,
                total_questions=QUESTIONS_PER_SUBJECT,
                context=context_text,
            )

            # 4. LLM call — wrapped per-subject so one failure doesn't abort the batch
            try:
                raw_response = self.llm.complete(
                    prompt=prompt,
                    cancel_event=cancel_event,
                    max_tokens=4096,
                    response_format={"type": "json_object"},
                )
                data = self._parse_json_response(raw_response)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "AssessmentGenerator: LLM call/parse failed for gap '%s': %s",
                    gap.competency,
                    exc,
                )
                continue

            # 5. Data mapping
            subject_name = data.get("subject", gap.competency)
            for q_data in data.get("questions", []):
                try:
                    item = self._build_item(
                        q_data, subject_name, gap_report.target_role, chunk_ids
                    )
                    problems = validate_item_semantics(item)
                    if problems:
                        logger.warning(
                            "AssessmentGenerator: item skipped for '%s': %s",
                            gap.competency,
                            problems,
                        )
                    else:
                        all_assessment_items.append(item)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "AssessmentGenerator: failed to build item for '%s': %s",
                        gap.competency,
                        exc,
                    )

        return AssessmentItemReport(
            target_role=gap_report.target_role,
            items=all_assessment_items,
        )

    @staticmethod
    def _parse_json_response(raw_response: str) -> dict:
        start = raw_response.find("{")
        end = raw_response.rfind("}")
        if start != -1 and end != -1 and end >= start:
            cleaned = raw_response[start : end + 1]
            return json.loads(cleaned)
        raise ValueError("No JSON object found in LLM response")

    def _build_item(
        self, data: dict, subject: str, target_role: str, source_chunk_ids: list[str]
    ) -> AssessmentItem:
        question_type = "multiple_choice"

        # Normalise options — LLM may return list, JSON-string, or dict
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
            options = [str(o).strip() for o in raw_options]

        options = [str(opt).strip() for opt in options]

        # Resolution step: LLM returns "B" — map to full option string "B) Option text"
        correct_answer_raw = str(data.get("correct_answer", "")).strip()

        if question_type == "multiple_choice" and options:
            # First try: exact letter match (new prompt format returns "B")
            letter = correct_answer_raw.rstrip(")").strip().upper()
            letter_matched = next(
                (opt for opt in options if opt.upper().startswith(f"{letter})")),
                None,
            )
            if letter_matched:
                correct_answer = letter_matched
            else:
                # Fallback: substring match (handles "B) Option text" full-string answers)
                correct_answer = next(
                    (
                        opt
                        for opt in options
                        if correct_answer_raw.lower() in opt.lower()
                        or opt.lower() in correct_answer_raw.lower()
                    ),
                    options[0],
                )
        else:
            correct_answer = correct_answer_raw

        return AssessmentItem(
            subject=subject,
            competency=data.get("competency", "General"),
            target_role=target_role,
            question_text=data.get("question", "Evaluate understanding"),
            question_type=question_type,
            options=options,
            correct_answer=correct_answer,
            distractor_rationales=data.get("distractor_rationales", {}),
            rationale=data.get("rationale", "Grounded via curriculum extraction."),
            difficulty="intermediate",
            source_chunk_ids=source_chunk_ids,
        )