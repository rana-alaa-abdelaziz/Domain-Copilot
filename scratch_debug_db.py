import json
import sys

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import Connection
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Find the most recent thread_id in review_tasks
engine = create_engine("postgresql://postgres:postgres@localhost:5432/domain_copilot")
with Session(engine) as session:
    result = session.execute(text("SELECT thread_id FROM review_task ORDER BY created_at DESC LIMIT 1")).first()
    if not result:
        print("No review tasks found")
        sys.exit(0)
    thread_id = result[0]
    print(f"Latest thread_id: {thread_id}")

with Connection.connect("postgresql://postgres:postgres@localhost:5432/domain_copilot") as conn:
    checkpointer = PostgresSaver(conn)
    config = {"configurable": {"thread_id": thread_id}}
    state = checkpointer.get(config)
    
    if state:
        val = state.get("channel_values", {})
        print("degraded:", val.get("degraded"))
        print("error:", val.get("error"))
        assess = val.get("assessment_report")
        if assess:
            print("assessment_report type:", type(assess))
            if isinstance(assess, dict):
                print(assess)
            else:
                try:
                    import json
                    print(json.dumps(assess.model_dump(), indent=2))
                except:
                    print("items:", getattr(assess, "items", None))
        else:
            print("No assessment_report")
    else:
        print("No state found")
