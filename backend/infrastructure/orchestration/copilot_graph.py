from typing import TypedDict

from langgraph.graph import END, StateGraph

from backend.application.agents.assessment_generator import AssessmentGenerator
from backend.application.agents.module_outline_generator import ModuleOutlineGenerator
from backend.application.agents.standards_mapper import StandardsMapper
from backend.domain.entities import CompetencyGapReport
from backend.domain.entities.assessment_item import AssessmentItemReport
from backend.domain.entities.module_outline import ModuleOutlineReport


class CopilotState(TypedDict):
    target_role: str
    user_reported_subjects: list[str]
    competency_gap_report: CompetencyGapReport | None
    module_outline_report: ModuleOutlineReport | None
    assessment_report: AssessmentItemReport | None


def create_copilot_graph(
    standards_mapper: StandardsMapper,
    outline_generator: ModuleOutlineGenerator | None = None,
    assessment_generator: AssessmentGenerator | None = None,
):
    workflow = StateGraph(CopilotState)

    def run_standards_mapper(state: CopilotState):
        report = standards_mapper.run(
            target_role=state["target_role"],
            user_reported_subjects=state["user_reported_subjects"],
        )
        return {"competency_gap_report": report}

    workflow.add_node("standards_mapper", run_standards_mapper)
    workflow.set_entry_point("standards_mapper")

    current_node = "standards_mapper"

    if outline_generator:

        def run_outline_generator(state: CopilotState):
            gap_report = state.get("competency_gap_report")
            outline_report = outline_generator.generate_outline(gap_report)
            return {"module_outline_report": outline_report}

        workflow.add_node("module_outline_generator", run_outline_generator)
        workflow.add_edge(current_node, "module_outline_generator")
        current_node = "module_outline_generator"

    if assessment_generator:

        def run_assessment_generator(state: CopilotState):
            gap_report = state.get("competency_gap_report")
            assessment_report = assessment_generator.generate_items(gap_report)
            return {"assessment_report": assessment_report}

        workflow.add_node("assessment_generator", run_assessment_generator)
        workflow.add_edge(current_node, "assessment_generator")
        current_node = "assessment_generator"

    workflow.add_edge(current_node, END)

    return workflow.compile()
