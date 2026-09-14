from typing import TypedDict, List, Optional
from langgraph.graph import StateGraph, END
from backend.domain.entities.competency_gap_report import CompetencyGapReport
from backend.domain.entities.module_outline import ModuleOutlineReport
from backend.domain.entities.assessment_item import AssessmentItemReport
from backend.application.agents.standards_mapper import StandardsMapper
from backend.application.agents.module_outline_generator import ModuleOutlineGenerator
from backend.application.agents.assessment_generator import AssessmentGenerator

class CopilotState(TypedDict):
    target_role: str
    user_reported_subjects: List[str]
    competency_gap_report: Optional[CompetencyGapReport]
    module_outline_report: Optional[ModuleOutlineReport]
    assessment_report: Optional[AssessmentItemReport]

def create_copilot_graph(
    standards_mapper: StandardsMapper, 
    outline_generator: ModuleOutlineGenerator,
    assessment_generator: AssessmentGenerator
):
    workflow = StateGraph(CopilotState)

    # Define nodes
    def run_standards_mapper(state: CopilotState):
        report = standards_mapper.run(
            target_role=state["target_role"],
            user_reported_subjects=state["user_reported_subjects"]
        )
        return {"competency_gap_report": report}

    def run_outline_generator(state: CopilotState):
        gap_report = state.get("competency_gap_report")
        outline_report = outline_generator.generate_outline(gap_report)
        return {"module_outline_report": outline_report}

    def run_assessment_generator(state: CopilotState):
        gap_report = state.get("competency_gap_report")
        assessment_report = assessment_generator.generate_items(gap_report)
        return {"assessment_report": assessment_report}

    workflow.add_node("standards_mapper", run_standards_mapper)
    workflow.add_node("module_outline_generator", run_outline_generator)
    workflow.add_node("assessment_generator", run_assessment_generator)

    # Define sequential edges
    workflow.set_entry_point("standards_mapper")
    workflow.add_edge("standards_mapper", "module_outline_generator")
    workflow.add_edge("module_outline_generator", "assessment_generator")
    workflow.add_edge("assessment_generator", END)

    return workflow.compile()