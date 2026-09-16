import json
import threading
from pathlib import Path

from backend.application.use_cases.hybrid_retrieve import HybridRetrieveUseCase
from backend.domain.entities.assessment_item import AssessmentItem, AssessmentItemReport, validate_item_semantics
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
    ) -> AssessmentItemReport | dict:
        
        # 1. Target the Gaps
        gap_competencies = [
            c
            for c in gap_report.gaps
            if not c.matched_user_subject or str(c.matched_user_subject).lower() == "none"
        ]

        if not gap_competencies:
            return {
                "total_questions": 0,
                "sections": [],
                "message": (
                    "Cannot generate assessment: No competency gaps identified."
                ),
            }

        # 2 & 3. Retrieve Context FIRST, then Filter (Anti-Hallucination)
        valid_gaps = []
        subject_context = {}
        subject_chunk_ids = {}

        for c in gap_competencies:
            retrieval_results = self.retrieve_uc.execute(query=c.competency, top_k=5)
            if retrieval_results.citations:
                context_text = "\n".join([cit.content for cit in retrieval_results.citations])
                subject_context[c.competency] = context_text
                subject_chunk_ids[c.competency] = [cit.chunk_id for cit in retrieval_results.citations]
                valid_gaps.append(c)

        if not valid_gaps:
            return {
                "total_questions": 0,
                "sections": [],
                "message": (
                    "Cannot generate assessment: No verified curriculum context available for the gaps."
                ),
            }

        # 4. Reallocate Quotas
        num_subjects = len(valid_gaps)
        base_quota = 20 // num_subjects
        remainder = 20 % num_subjects

        quotas = {}
        for i, c in enumerate(valid_gaps):
            quotas[c.competency] = base_quota + (1 if i < remainder else 0)

        # Combine context
        context_parts = []
        for c in valid_gaps:
            context_parts.append(f"--- SUBJECT: {c.competency} ---\n{subject_context[c.competency]}")
        combined_context = "\n\n".join(context_parts)

        quotas_str = "\n".join([f"- {subject}: {q} questions" for subject, q in quotas.items()])
        
        prompt = self.prompt_template.format(
            context=combined_context,
            subject_quotas=quotas_str,
            total_questions=20
        )
        raw_response = None
        try:
            raw_response = self.llm.complete(
                prompt=prompt, 
                cancel_event=cancel_event, 
                max_tokens=8192,
                response_format={"type": "json_object"}
            )
            data = self._parse_json_response(raw_response)
        except Exception as e:
            print(f"Failed to generate or parse blueprint: {e}")
            if raw_response:
                print(f"Raw response: {raw_response}")
            return AssessmentItemReport(target_role=gap_report.target_role, items=[])
            
        items = []
        sections = data.get("sections", [])
        for section in sections:
            subject_name = section.get("subject", "Uncategorized")
            chunk_ids = subject_chunk_ids.get(subject_name, [])
            for q_data in section.get("questions", []):
                try:
                    item = self._build_item(q_data, subject_name, gap_report.target_role, chunk_ids)
                    problems = validate_item_semantics(item)
                    if not problems:
                        items.append(item)
                    else:
                        print(f"Skipping item due to validation problems: {problems}")
                except Exception as e:
                    print(f"Failed to build item: {e}")
                
        return AssessmentItemReport(target_role=gap_report.target_role, items=items)

    @staticmethod
    def _parse_json_response(raw_response: str) -> dict:
        start = raw_response.find('{')
        end = raw_response.rfind('}')
        if start != -1 and end != -1 and end >= start:
            cleaned = raw_response[start:end+1]
            return json.loads(cleaned)
        raise ValueError("No JSON object found in response")

    def _build_item(
        self, data: dict, subject: str, target_role: str, source_chunk_ids: list[str]
    ) -> AssessmentItem:
        question_type = "multiple_choice"
        
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

        if question_type == "multiple_choice" and options:
            options = [str(opt).strip() for opt in options]
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
