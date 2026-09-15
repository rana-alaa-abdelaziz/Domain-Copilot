"""
Standards Mapper agent with absolute domain partitioning.
Guarantees zero cross-domain citation contamination (e.g., SQL skills cannot match API curriculum).

Clean Architecture boundary: Plain Python class with ZERO framework, SDK,
or LangGraph imports.
"""

import contextlib
import json
import re
import threading
from pathlib import Path

from backend.application.use_cases.hybrid_retrieve import HybridRetrieveUseCase
from backend.domain.entities.competency_gap_report import (
    CompetencyGap,
    CompetencyGapReport,
)
from backend.domain.ports import LlmProvider

DEFAULT_PROMPT_PATH = (
    Path(__file__).resolve().parents[3] / "prompts" / "v1" / "standards_mapper.md"
)

# Mutually exclusive domain categories
DOMAIN_KEYWORDS = {
    "api": {"api", "rest", "graphql", "endpoint"},
    "git": {"git", "version", "control", "github", "gitlab"},
    "sql": {"sql", "database", "relational", "postgres", "mysql", "db", "modeling"},
    "test": {"test", "testing", "qa", "pytest", "unit", "mock", "debugging"},
    "docker": {"docker", "container", "containerization"},
}

GENERIC_STOPWORDS = {
    "design",
    "development",
    "management",
    "implementation",
    "system",
    "systems",
    "applications",
    "application",
    "software",
    "engineering",
    "service",
    "services",
    "basics",
    "fundamentals",
    "advanced",
    "core",
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

    @staticmethod
    def _parse_skills_list(text: str) -> list[str]:
        """Extracts list of skill strings from raw LLM text."""
        text = text.strip()
        with contextlib.suppress(json.JSONDecodeError):
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(s).strip() for s in parsed if str(s).strip()]

        matches = re.findall(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
        for m in matches:
            with contextlib.suppress(json.JSONDecodeError):
                parsed = json.loads(m)
                if isinstance(parsed, list):
                    return [str(s).strip() for s in parsed if str(s).strip()]

        raw_list = re.search(r"\[(.*?)\]", text, re.DOTALL)
        if raw_list:
            items = raw_list.group(1).split(",")
            return [i.strip(" '\"\n\r") for i in items if i.strip(" '\"\n\r")]

        return []

    @staticmethod
    def _find_matching_subject(
        skill: str, user_reported_subjects: list[str]
    ) -> str | None:
        """
        Absolute domain partitioning check. Ensures cross-domain contamination is blocked.
        """

        # Tokenize to avoid substring bugs (e.g. "api" in "rapid", "rest" in "interest")
        def get_tokens(text: str) -> set[str]:
            return set(re.findall(r"\b\w+\b", text.lower()))

        skill_tokens = get_tokens(skill)

        def get_domain(tokens: set[str]) -> str | None:
            for domain, keywords in DOMAIN_KEYWORDS.items():
                if tokens.intersection(keywords):
                    return domain
            return None

        skill_domain = get_domain(skill_tokens)

        best_match = None
        best_score = 0

        for subject in user_reported_subjects:
            subject_tokens = get_tokens(subject)
            subject_domain = get_domain(subject_tokens)

            # 1. Enforce cross-domain boundary (Absolute block)
            if skill_domain and subject_domain and skill_domain != subject_domain:
                continue

            # 2. Calculate meaningful textual overlap
            meaningful_skill = skill_tokens - GENERIC_STOPWORDS
            meaningful_subject = subject_tokens - GENERIC_STOPWORDS
            overlap = len(meaningful_skill.intersection(meaningful_subject))

            score = overlap

            # 3. Same domain boost
            if skill_domain and skill_domain == subject_domain:
                score += 2  # Boost for matching domain

            # 4. Fallback for unrecognized domains
            if score == 0:
                skill_lower = skill.lower()
                subject_lower = subject.lower()
                # Substring fallback
                if subject_lower in skill_lower or skill_lower in subject_lower:
                    score = 1

            if score > best_score:
                best_score = score
                best_match = subject

        return best_match

    def run(
        self,
        target_role: str,
        user_reported_subjects: list[str],
        cancel_event: "threading.Event | None" = None,
    ) -> CompetencyGapReport:
        # 1. Retrieve Role Requirements (Side 1)
        req_retrieval = self._retrieve.execute(
            query=f"{target_role} technical skills core competencies requirements",
            top_k=4,
            doc_category="requirement",
        )
        req_citations = req_retrieval.citations
        req_evidence = "\n\n".join(
            [f"[{c.chunk_id}] {c.content.strip()[:400]}" for c in req_citations]
        )

        # 2. Retrieve Candidate Reference Curriculum (Side 2)
        curriculum_by_subject: dict[str, list] = {}
        for subject in user_reported_subjects:
            subj_retrieval = self._retrieve.execute(
                query=subject, top_k=3, doc_category="reference_curriculum"
            )
            curriculum_by_subject[subject] = subj_retrieval.citations

        # 3. Ask LLM to extract the list of required competencies
        with open(self._prompt_path, encoding="utf-8") as f:
            template = f.read()

        prompt = template.format(
            target_role=target_role,
            requirements_evidence=req_evidence,
        )

        llm_output = self._llm_provider.complete(
            prompt=prompt,
            cancel_event=cancel_event,
            options={"temperature": 0.0, "num_ctx": 2048},
        )
        extracted_skills = self._parse_skills_list(llm_output)


        if not extracted_skills:
 
            extracted_skills = [f"Core Competencies in {subject}" for subject in user_reported_subjects]
            
            if not extracted_skills:
                extracted_skills = [f"Foundational Standards for {target_role}"]

        # 4. Strict Deterministic Matching with Absolute Domain Partitioning
        gaps: list[CompetencyGap] = []

        for skill in extracted_skills:
            skill_lower = skill.lower()
            skill_tokens = {
                w
                for w in skill_lower.split()
                if len(w) >= 2 and w not in GENERIC_STOPWORDS
            }

            matched_subject = self._find_matching_subject(skill, user_reported_subjects)

            coverage_chunk_ids: list[str] = []
            coverage_source = "unverified"
            severity = "critical"

            if matched_subject:
                citations = curriculum_by_subject.get(matched_subject, [])
                relevant_citations = [
                    c
                    for c in citations
                    if any(tok in c.content.lower() for tok in skill_tokens)
                    or not skill_tokens
                ]
                if relevant_citations:
                    coverage_chunk_ids = [c.chunk_id for c in relevant_citations]
                    coverage_source = "corpus_citation"
                    severity = "minor"

            # Find requirement chunk citation by text overlap
            req_chunk_ids = [
                c.chunk_id
                for c in req_citations
                if any(w in c.content.lower() for w in skill_tokens)
            ]
            if not req_chunk_ids and req_citations:
                req_chunk_ids = [req_citations[0].chunk_id]

            gaps.append(
                CompetencyGap(
                    competency=skill,
                    required_by_chunk_ids=req_chunk_ids,
                    coverage_source=coverage_source,
                    severity=severity,
                    coverage_chunk_ids=coverage_chunk_ids,
                    matched_user_subject=matched_subject,
                )
            )

        return CompetencyGapReport(
            target_role=target_role,
            user_reported_subjects=list(user_reported_subjects),
            gaps=gaps,
        )
