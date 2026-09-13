"""
Standards Mapper agent.
Composes HybridRetrieveUseCase and LlmProvider to identify role competencies
from requirement documents and evaluate candidate subject coverage against
reference curriculum documents.

Clean Architecture boundary: Plain Python class with ZERO framework, SDK,
or LangGraph imports.
"""
import json
from pathlib import Path
from typing import Any

from backend.application.use_cases.hybrid_retrieve import HybridRetrieveUseCase
from backend.domain.entities.competency_gap_report import (
    CompetencyGap,
    CompetencyGapReport,
)
from backend.domain.ports import LlmProvider

DEFAULT_PROMPT_PATH = (
    Path(__file__).resolve().parents[3] / "prompts" / "v1" / "standards_mapper.md"
)

SUBMIT_GAP_REPORT_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_competency_gap_report",
        "description": "Submit structured competency gap report comparing target role against candidate subjects",
        "parameters": {
            "type": "object",
            "properties": {
                "target_role": {"type": "string"},
                "user_reported_subjects": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "gaps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "competency": {"type": "string"},
                            "required_by_chunk_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "coverage_source": {
                                "type": "string",
                                "enum": [
                                    "corpus_citation",
                                    "model_inference",
                                    "unverified",
                                ],
                            },
                            "severity": {
                                "type": "string",
                                "enum": ["critical", "moderate", "minor"],
                            },
                            "coverage_chunk_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "matched_user_subject": {
                                "type": ["string", "null"],
                            },
                        },
                        "required": [
                            "competency",
                            "required_by_chunk_ids",
                            "coverage_source",
                            "severity",
                        ],
                    },
                },
            },
            "required": ["target_role", "user_reported_subjects", "gaps"],
        },
    },
}


class StandardsMapper:
    def __init__(
        self,
        retrieve_use_case: HybridRetrieveUseCase,
        llm_provider: LlmProvider,
        prompt_path: Path | None = None,
    ):
        self._retrieve = retrieve_use_case
        self._llm_provider = llm_provider
        self._prompt_path = prompt_path or DEFAULT_PROMPT_PATH

    def _extract_arguments(self, response: Any) -> dict:
        """Robustly extracts tool arguments from various LLM provider response formats."""
        if not isinstance(response, dict):
            return {}

        # 1. Direct "arguments" key
        if "arguments" in response:
            args = response["arguments"]
            if isinstance(args, str):
                try:
                    return json.loads(args)
                except Exception:
                    return {}
            if isinstance(args, dict):
                return args

        # 2. Standard OpenAI/Ollama tool_calls list
        tool_calls = response.get("tool_calls") or []
        if not tool_calls and "message" in response:
            tool_calls = response["message"].get("tool_calls") or []

        if tool_calls and isinstance(tool_calls, list):
            first_call = tool_calls[0]
            func = first_call.get("function", {}) if isinstance(first_call, dict) else {}
            args = func.get("arguments", {})
            if isinstance(args, str):
                try:
                    return json.loads(args)
                except Exception:
                    return {}
            if isinstance(args, dict):
                return args

        # 3. Fallback: Check if response itself contains "gaps"
        if "gaps" in response:
            return response

        return {}

    def run(
        self, target_role: str, user_reported_subjects: list[str]
    ) -> CompetencyGapReport:
        # 1. Scoped retrieval for role requirements (Side 1)
        req_retrieval = self._retrieve.execute(
            query=target_role, top_k=5, doc_category="requirement"
        )
        req_lines = []
        for cit in req_retrieval.citations:
            req_lines.append(f"[{cit.chunk_id}] {cit.content.strip()}")
        requirements_evidence = (
            "\n\n".join(req_lines)
            if req_lines
            else "No role requirement evidence retrieved."
        )

        # 2. Scoped retrieval per user subject against reference curriculum (Side 2)
        curriculum_lines = []
        for subject in user_reported_subjects:
            subj_retrieval = self._retrieve.execute(
                query=subject, top_k=3, doc_category="reference_curriculum"
            )
            for cit in subj_retrieval.citations:
                curriculum_lines.append(
                    f"[{cit.chunk_id}] (Subject: {subject}) {cit.content.strip()}"
                )
        curriculum_evidence = (
            "\n\n".join(curriculum_lines)
            if curriculum_lines
            else "No reference curriculum evidence retrieved."
        )

        # 3. Load and format versioned prompt
        with open(self._prompt_path, encoding="utf-8") as f:
            template = f.read()

        prompt = template.format(
            target_role=target_role,
            user_reported_subjects=", ".join(user_reported_subjects),
            requirements_evidence=requirements_evidence,
            curriculum_evidence=curriculum_evidence,
        )

        # 4. Invoke LLM structured tool calling
        response = self._llm_provider.call_tool(
            prompt=prompt, tools=[SUBMIT_GAP_REPORT_TOOL]
        )

        args = self._extract_arguments(response)
        raw_gaps = args.get("gaps", [])
        gaps = []
        for g in raw_gaps:
            # Handle cases where the item is a serialized JSON string or a plain string title
            if isinstance(g, str):
                try:
                    parsed = json.loads(g)
                    g = parsed if isinstance(parsed, dict) else {"competency": g}
                except Exception:
                    g = {"competency": g}
            elif not isinstance(g, dict):
                continue

            coverage_source = g.get("coverage_source", "unverified")
            if coverage_source not in {"corpus_citation", "model_inference", "unverified"}:
                coverage_source = "unverified"

            severity = g.get("severity", "moderate")
            if severity not in {"critical", "moderate", "minor"}:
                severity = "moderate"

            # Fallback: Grounding safeguard if model omits required_by_chunk_ids
            req_chunk_ids = list(g.get("required_by_chunk_ids", []))
            if not req_chunk_ids and req_retrieval.citations:
                req_chunk_ids = [req_retrieval.citations[0].chunk_id]

            gaps.append(
                CompetencyGap(
                    competency=g.get("competency", "Unspecified competency"),
                    required_by_chunk_ids=req_chunk_ids,
                    coverage_source=coverage_source,
                    severity=severity,
                    coverage_chunk_ids=list(g.get("coverage_chunk_ids", [])),
                    matched_user_subject=g.get("matched_user_subject"),
                )
            )

        return CompetencyGapReport(
            target_role=target_role,
            user_reported_subjects=list(user_reported_subjects),
            gaps=gaps,
        )