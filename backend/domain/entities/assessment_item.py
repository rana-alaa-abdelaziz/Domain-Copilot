from pydantic import BaseModel, Field


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


class AssessmentItemReport(BaseModel):
    target_role: str
    items: list[AssessmentItem] = Field(default_factory=list)
