"""
Custom orchestration exceptions for agent execution and loop limits.
"""


class OrchestrationError(Exception):
    """Base exception for all orchestration and agent runtime errors."""


class AgentTimeoutError(OrchestrationError):
    """Raised when an agent execution exceeds its allotted time threshold."""

    def __init__(self, agent_name: str, timeout_seconds: float):
        super().__init__(f"Agent '{agent_name}' exceeded timeout of {timeout_seconds} seconds.")
        self.agent_name = agent_name
        self.timeout_seconds = timeout_seconds


class MaxIterationsExceededError(OrchestrationError):
    """Raised when a graph node or iterative refinement loop exceeds maximum allowed iterations."""

    def __init__(self, node_name: str, max_iterations: int):
        super().__init__(f"Graph node '{node_name}' exceeded maximum allowed iterations ({max_iterations}).")
        self.node_name = node_name
        self.max_iterations = max_iterations


class ClientCancelledError(OrchestrationError):
    """Raised when a background task or agent call is aborted due to client disconnection."""

    def __init__(self, message: str = "Client cancelled the request."):
        super().__init__(message)