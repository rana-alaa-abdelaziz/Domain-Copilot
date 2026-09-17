import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.infrastructure.db.models import LlmCallRecordModel

engine = create_engine("postgresql://postgres:postgres@localhost:5432/domain_copilot")
with Session(engine) as session:
    records = session.query(LlmCallRecordModel).filter_by(thread_id="1b1ae95d-3036-400d-9529-3156b5de7d08").all()
    if not records:
        print("No LLM calls found for this thread.")
        sys.exit(0)
    
    for r in records:
        if r.agent_name == "AssessmentGenerator":
            print(f"--- LLM Call: {r.call_id} ---")
            print("Prompt length:", r.prompt_tokens)
            print("Completion length:", r.completion_tokens)
            # wait, the DB might only store tokens and not the actual text payload
            # Let's check what fields LlmCallRecordModel has.
