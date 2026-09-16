import asyncio
import sys

from fastapi.testclient import TestClient

from backend.main import app


def run_observability_check():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    with TestClient(app):
        # 1. Trigger an LLM call through the system. We can use the streaming_router or any agent.
        # But wait, there is no direct generic LLM endpoint, RAG is under /stream maybe?
        # Let's just create a trace or see if we can trigger the Copilot Graph.
        
        # We can also just use the db_session and AccountingProvider directly
        from backend.infrastructure.api.correlation_middleware import _correlation_id
        from backend.infrastructure.db.repositories.llm_call_repository import (
            SqlAlchemyLlmCallRepository,
        )
        
        session = app.state.db_session
        llm = app.state.llm_provider
        
        # If it's AccountingProvider, let's just use it to generate
        token = _correlation_id.set("eval-observability-run")
        try:
            prompt = "What is the capital of France? Return just the city name."
            res = llm.complete(prompt)
            print(f"LLM Response: {res}")
            
            repo = SqlAlchemyLlmCallRepository(session)
            calls = repo.list_by_correlation_id("eval-observability-run")
            print(f"Total Calls for correlation: {len(calls)}")
            
            if calls:
                call = calls[-1]
                print(f"Model: {call.model}")
                print(f"Prompt tokens: {call.prompt_tokens}")
                print(f"Completion tokens: {call.completion_tokens}")
                print(f"Estimated Cost: ${call.estimated_cost_usd:.6f}")
                
                with open("docs/EVALUATION.md", "a") as f:
                    f.write("\n### FR-9: Observability Cost Tracking\n")
                    f.write(f"- **Model**: {call.model}\n")
                    f.write(f"- **Prompt Tokens**: {call.prompt_tokens}\n")
                    f.write(f"- **Completion Tokens**: {call.completion_tokens}\n")
                    f.write(f"- **Estimated Cost**: ${call.estimated_cost_usd:.6f}\n")
                    f.write("- **Result**: Successfully tracked via AccountingProvider and persisted to LlmCallRecord table.\n")
                    f.write("\n")
        finally:
            _correlation_id.reset(token)

if __name__ == "__main__":
    run_observability_check()
