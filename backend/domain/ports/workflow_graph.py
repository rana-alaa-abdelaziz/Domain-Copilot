"""
Port abstracting the orchestration graph's runtime interface — get/update
state, resume execution. Exists so application/use_cases/human_review_service.py
depends on this shape, not on langgraph.graph.state.CompiledStateGraph
directly, keeping LangGraph confined to infrastructure/orchestration/.
"""
from typing import Any, Protocol


class WorkflowGraphPort(Protocol):
    def get_state(self, config: dict) -> Any: ...
    def update_state(self, config: dict, values: dict) -> None: ...
    def invoke(self, input: Any, config: dict) -> dict: ...