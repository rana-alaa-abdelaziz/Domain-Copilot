from pydantic import BaseModel, Field, model_validator


class AssessmentItem(BaseModel):
    subject: str = Field(default="Uncategorized", description="Subject category for this item")
    competency: str = Field(..., description="The unverified competency being tested")
    target_role: str = Field(..., description="The target role for this assessment")
    question_text: str = Field(
        ..., description="The generated technical assessment question"
    )
    question_type: str = Field(
        default="multiple_choice",
        description="Type: multiple_choice, coding, or short_answer",
    )
    options: list[str] = Field(
        default_factory=list, description="List of choices if multiple_choice"
    )
    correct_answer: str = Field(
        ..., description="The correct answer or key solution concept"
    )
    rationale: str = Field(
        ...,
        description="Explanation of why the answer is correct and maps to the competency",
    )
    distractor_rationales: dict[str, str] = Field(
        default_factory=dict,
        description="Plausible rationales for each incorrect option",
    )
    difficulty: str = Field(
        default="intermediate", description="beginner, intermediate, or advanced"
    )
    source_chunk_ids: list[str] = Field(
        default_factory=list,
        description="Chunk IDs the retrieved evidence for this item came from — "
        "traceability back to source material, required for grounding.",
    )

    @model_validator(mode="after")
    def validate_options_and_answer(self) -> "AssessmentItem":
        """Quality Gate: Ensures multiple-choice items have valid options and a matching correct answer."""
        if self.question_type == "multiple_choice":
            if not self.options or len(self.options) < 2:
                raise ValueError("Multiple-choice assessment items must have at least 2 options.")
            if self.correct_answer not in self.options:
                raise ValueError(
                    f"Correct answer '{self.correct_answer}' must be present in the provided options: {self.options}"
                )
            
            # Simple prefix-based check for matching options to distractor keys
            option_prefixes = [opt[0] for opt in self.options if len(opt) > 0 and opt[1:2] in {')', '.'}]
            if option_prefixes and not self.distractor_rationales:
                pass # Accept it if LLM didn't format perfectly, validation below will catch real issues
                
        if not self.question_text or len(self.question_text.strip()) < 5:
            raise ValueError("Question text must be at least 5 characters long.")
        return self


class AssessmentItemReport(BaseModel):
    target_role: str
    items: list[AssessmentItem] = Field(default_factory=list)


def validate_item_semantics(item: AssessmentItem) -> list[str]:
    """Returns a list of problems found; empty list = passes. This is
    the deterministic auto-validation pass D3 requires — catches
    plausible-but-wrong items an LLM produced, including the specific
    failure mode found in Q2/Q6 (correct_answer not among options,
    rationale containing leaked error text)."""
    problems = []

    if item.correct_answer not in item.options:
        problems.append(
            f"correct_answer '{item.correct_answer[:60]}...' is not one "
            f"of the provided options — likely a parse-failure fallback"
        )

    if not item.question_text.strip().endswith("?"):
        problems.append(
            "question_text does not read as a question — likely a "
            "fallback 'explain X' template rather than a real MCQ stem"
        )

    error_leak_markers = ["parser exception", "Expecting value", "Traceback", "generated dynamically"]
    if any(marker.lower() in item.rationale.lower() for marker in error_leak_markers):
        problems.append("rationale contains what appears to be a leaked error message")

    if len(item.options) < 2 or len(set(item.options)) != len(item.options):
        problems.append("options list has duplicates or fewer than 2 entries")

    if item.question_type == "multiple_choice" and not item.distractor_rationales:
        problems.append("multiple_choice item is missing distractor_rationales")

    return problems