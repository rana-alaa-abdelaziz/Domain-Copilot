from unittest.mock import Mock

from backend.domain.entities import CompetencyGapReport
from backend.domain.entities.assessment_item import AssessmentItemReport
from backend.domain.entities.module_outline import ModuleOutlineReport
from backend.infrastructure.orchestration.copilot_graph import (
    create_copilot_graph,
)


def test_rejected_review_never_publishes():
    """
    Test that a rejected human review correctly routes to END
    and never reaches the publish_curriculum node.
    """
    standards_mapper = Mock()
    outline_generator = Mock()
    assessment_generator = Mock()
    review_task_repo = Mock()
    pub_repo = Mock()
    
    graph = create_copilot_graph(
        standards_mapper=standards_mapper,
        outline_generator=outline_generator,
        assessment_generator=assessment_generator,
        review_task_repository=review_task_repo,
        published_curriculum_repository=pub_repo
    )
    
    # Simulate state already past human review breakpoint with 'rejected' status

    
    # To test routing from human review directly, we invoke the graph starting at human_review,
    # or just test the conditional edge directly since the graph doesn't allow easy step testing without a checkpointer.
    # The simplest way is to extract the conditional edge logic or test via full invoke if it allows bypassing.
    # Actually, we can run a single state through the `route_after_review` function to be very precise.
    
    # We can inspect the graph nodes and edges if we want, but it's easier to just run the edge function if it was accessible.
    # Since it's nested, we'll invoke the graph from the human_review node if possible, or just look at what happens.
    
    # Let's mock the methods to see what happens
    config = {"configurable": {"thread_id": "test-thread"}}
    
    # If we pass state in, it starts at entrypoint. So we mock standards_mapper etc. to just pass through,
    # But wait, it hits interrupt_before=["human_review"].
    # To test this perfectly:
    # 1. Provide an in-memory checkpointer.
    from langgraph.checkpoint.memory import MemorySaver
    checkpointer = MemorySaver()
    
    graph = create_copilot_graph(
        standards_mapper=standards_mapper,
        outline_generator=outline_generator,
        assessment_generator=assessment_generator,
        checkpointer=checkpointer,
        review_task_repository=review_task_repo,
        published_curriculum_repository=pub_repo
    )
    
    # Mock node outputs to get to human review
    standards_mapper.run.return_value = CompetencyGapReport(target_role="expert", user_reported_subjects=[], gaps=[])
    outline_generator.generate_outline.return_value = ModuleOutlineReport(target_role="expert", modules=[])
    assessment_generator.generate_items.return_value = AssessmentItemReport(target_role="expert", items=[])
    
    # 1. Run until human_review breakpoint
    graph.invoke({
        "target_role": "expert",
        "user_reported_subjects": [],
    }, config)
    
    # Verify it stopped
    state_info = graph.get_state(config)
    assert "human_review" in state_info.next
    
    # 2. Update state to rejected and resume
    graph.update_state(config, {"review_status": "rejected"})
    graph.invoke(None, config)
    
    # 3. Verify pub_repo.save was NEVER called
    pub_repo.save.assert_not_called()
    
    # Let's also verify that if it's approved, it IS called
    # Reset mocks
    pub_repo.save.reset_mock()
    pub_repo.get_by_thread_id.return_value = None
    config_approved = {"configurable": {"thread_id": "test-thread-2"}}
    graph.invoke({
        "target_role": "expert",
        "user_reported_subjects": [],
        "competency_gap_report": CompetencyGapReport(target_role="expert", user_reported_subjects=[], gaps=[]),
        "module_outline_report": ModuleOutlineReport(target_role="expert", modules=[]),
        "assessment_report": AssessmentItemReport(target_role="expert", items=[]),
    }, config_approved)
    
    state_info2 = graph.get_state(config_approved)
    assert "human_review" in state_info2.next
    
    graph.update_state(config_approved, {"review_status": "approved"})
    graph.invoke(None, config_approved)
    
    # It should have called save
    pub_repo.save.assert_called_once()
