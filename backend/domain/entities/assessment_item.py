from pydantic import BaseModel, Field, model_validator


class AssessmentItem(BaseModel):
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
        if not self.question_text or len(self.question_text.strip()) < 5:
            raise ValueError("Question text must be at least 5 characters long.")
        return self


class AssessmentItemReport(BaseModel):
    target_role: str
    items: list[AssessmentItem] = Field(default_factory=list)