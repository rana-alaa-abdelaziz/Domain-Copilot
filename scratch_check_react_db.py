from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


def check_db():
    engine = create_engine("postgresql://postgres:postgres@localhost:5432/domain_copilot")
    with Session(engine) as session:
        # Check if the text "ReactJSNotesForProfessionals" is in any chunk
        chunks = session.execute(text("SELECT doc_id FROM chunk WHERE content ILIKE '%React%';")).fetchall()
        print(f"Chunks containing 'React': {len(chunks)}")
        if chunks:
            # Get the distinct doc_ids
            doc_ids = {c[0] for c in chunks}
            print("Doc IDs with React:", doc_ids)
            
            # Show names of these doc_ids
            docs = session.execute(text("SELECT doc_id, source FROM document WHERE doc_id = ANY(:doc_ids)"), {"doc_ids": list(doc_ids)}).fetchall()
            print("Documents containing React:", docs)

if __name__ == "__main__":
    check_db()
