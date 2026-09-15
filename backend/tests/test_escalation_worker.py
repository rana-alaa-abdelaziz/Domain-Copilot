from datetime import datetime, timezone
from unittest.mock import Mock

from backend.application.use_cases.escalation_worker import EscalationWorkerUseCase
from backend.domain.entities.review_task import ReviewTask


def test_execute_no_overdue_tasks():
    repo_mock = Mock()
    repo_mock.list_overdue.return_value = []
    
    worker = EscalationWorkerUseCase(review_task_repository=repo_mock)
    escalated_count = worker.execute()
    
    assert escalated_count == 0
    repo_mock.list_overdue.assert_called_once()
    repo_mock.update_status.assert_not_called()

def test_execute_overdue_but_not_pending():
    repo_mock = Mock()
    # Task is overdue but status is 'in_review'
    task = ReviewTask(
        review_task_id="task-1",
        thread_id="thread-1",
        item_id="item-1",
        target_role="expert",
        status="in_review",
        priority="high",
        sla_due_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo_mock.list_overdue.return_value = [task]
    
    worker = EscalationWorkerUseCase(review_task_repository=repo_mock)
    escalated_count = worker.execute()
    
    assert escalated_count == 0
    repo_mock.update_status.assert_not_called()

def test_execute_escalates_pending_tasks():
    repo_mock = Mock()
    task1 = ReviewTask(
        review_task_id="task-1",
        thread_id="thread-1",
        item_id="item-1",
        target_role="expert",
        status="pending",
        priority="high",
        sla_due_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    task2 = ReviewTask(
        review_task_id="task-2",
        thread_id="thread-2",
        item_id="item-2",
        target_role="expert",
        status="pending",
        priority="high",
        sla_due_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo_mock.list_overdue.return_value = [task1, task2]
    
    worker = EscalationWorkerUseCase(review_task_repository=repo_mock)
    escalated_count = worker.execute()
    
    assert escalated_count == 2
    assert repo_mock.update_status.call_count == 2
    repo_mock.update_status.assert_any_call("task-1", "escalated")
    repo_mock.update_status.assert_any_call("task-2", "escalated")

def test_execute_handles_exceptions_gracefully(caplog):
    repo_mock = Mock()
    task1 = ReviewTask(
        review_task_id="task-1",
        thread_id="thread-1",
        item_id="item-1",
        target_role="expert",
        status="pending",
        priority="high",
        sla_due_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    task2 = ReviewTask(
        review_task_id="task-2",
        thread_id="thread-2",
        item_id="item-2",
        target_role="expert",
        status="pending",
        priority="high",
        sla_due_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    repo_mock.list_overdue.return_value = [task1, task2]
    
    # Fail on the first task, succeed on the second
    def update_status_side_effect(task_id, status):
        if task_id == "task-1":
            raise ValueError("DB error")
    
    repo_mock.update_status.side_effect = update_status_side_effect
    
    worker = EscalationWorkerUseCase(review_task_repository=repo_mock)
    escalated_count = worker.execute()
    
    assert escalated_count == 1
    assert repo_mock.update_status.call_count == 2
    repo_mock.update_status.assert_any_call("task-1", "escalated")
    repo_mock.update_status.assert_any_call("task-2", "escalated")
    
    assert "Failed to escalate review task task-1: DB error" in caplog.text
