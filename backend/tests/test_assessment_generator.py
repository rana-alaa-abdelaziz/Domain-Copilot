
from backend.application.agents.assessment_generator import AssessmentGenerator
from backend.domain.entities.assessment_item import (
    AssessmentItem,
    AssessmentItemReport,
    validate_item_semantics,
)
from backend.domain.entities.competency_gap_report import (
    CompetencyGap,
    CompetencyGapReport,
)
from backend.domain.ports import LlmProvider


def test_item_with_answer_not_in_options_fails_semantic_validation():
    item = AssessmentItem(
        competency="Database Management",
        target_role="Junior Backend Developer",
        question_text="Explain database management",  # not a real question
        question_type="short_answer",
        options=["A", "B", "C", "D"],
        correct_answer="A Junior Backend Developer typically reaches proficient level within twelve to eighteen months...",  # the actual broken content found
        rationale="Generated dynamically from corpus context due to parser exception: Expecting value: line 1 column 1 (char 0)",
        source_chunk_ids=["c1"],
    )
    problems = validate_item_semantics(item)
    assert len(problems) >= 2  # both the bad answer AND the leaked error text should be caught


class FakeAlwaysEmptyLLM(LlmProvider):
    def complete(self, prompt: str, cancel_event=None, **kwargs) -> str:
        return ""
    def call_tool(self, prompt, tool, cancel_event=None, **kwargs):
        return ""
    def embed(self, text, cancel_event=None, **kwargs):
        return []
    def stream(self, prompt, cancel_event=None, **kwargs):
        yield ""
    def get_last_usage(self):
        return {}


class FakeRetrieveUseCase:
    def execute(self, query: str, top_k: int):
        class Citation:
            content = "some context"
            chunk_id = "c1"
        
        class Result:
            def __init__(self):
                self.citations = [Citation()]
            
        return Result()


def test_assessment_generator_returns_empty_when_no_gaps():
    """If ALL competencies are already matched (no gaps), the generator returns an empty report."""
    llm = FakeAlwaysEmptyLLM()
    retrieve_uc = FakeRetrieveUseCase()
    generator = AssessmentGenerator(retrieve_use_case=retrieve_uc, llm_provider=llm)

    gap_report_all_known = CompetencyGapReport(
        target_role="Junior Backend Developer",
        gaps=[
            CompetencyGap(
                competency="Database Management",
                severity="critical",
                coverage_source="unverified",
                matched_user_subject="SQL",  # user KNOWS this subject — not a gap
            )
        ],
    )

    report = generator.generate_items(gap_report_all_known)
    assert isinstance(report, AssessmentItemReport)
    assert len(report.items) == 0


class FakeJSONLLM(LlmProvider):
    """Returns the new per-subject JSON schema: {subject, questions[]}."""
    def complete(self, prompt: str, cancel_event=None, **kwargs) -> str:
        return """
        {
          "subject": "Comp A",
          "questions": [
            {
              "question_number": 1,
              "competency": "Comp A",
              "question": "Test Q1?",
              "options": ["A) 1", "B) 2", "C) 3", "D) 4"],
              "correct_answer": "B",
              "distractor_rationales": {"A": "wrong", "C": "wrong", "D": "wrong"},
              "rationale": "Because 2"
            }
          ]
        }
        """
    def call_tool(self, prompt, tool, cancel_event=None, **kwargs):
        return ""
    def embed(self, text, cancel_event=None, **kwargs):
        return []
    def stream(self, prompt, cancel_event=None, **kwargs):
        yield ""
    def get_last_usage(self):
        return {}


def test_assessment_generator_parses_per_subject_json():
    """Generator correctly maps letter correct_answer 'B' to full option string."""
    llm = FakeJSONLLM()
    retrieve_uc = FakeRetrieveUseCase()
    generator = AssessmentGenerator(retrieve_use_case=retrieve_uc, llm_provider=llm)

    gap_report = CompetencyGapReport(
        target_role="Junior Backend Developer",
        gaps=[
            CompetencyGap(
                competency="Comp A",
                severity="critical",
                coverage_source="unverified",
                matched_user_subject=None,  # This IS a gap — no known subject
            )
        ],
    )

    report = generator.generate_items(gap_report)
    assert isinstance(report, AssessmentItemReport)
    assert len(report.items) == 1
    item = report.items[0]
    # subject comes from the LLM's "subject" field
    assert item.subject == "Comp A"
    assert item.question_text == "Test Q1?"
    # letter "B" must be resolved to the full option string
    assert item.correct_answer == "B) 2"
    assert "wrong" in item.distractor_rationales["A"]
    assert item.source_chunk_ids == ["c1"]
