from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.infrastructure.db.models import Document

engine = create_engine("postgresql://postgres:postgres@localhost:5432/domain_copilot")
with Session(engine) as session:
    docs = session.query(Document).all()
    print("DOCS:", len(docs))
    for d in docs:
        print("  -", d.source)
