import os
import sys
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add the root of the project to PYTHONPATH so we can import backend
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.domain.entities.user import Role, User
from backend.infrastructure.auth.password_hashing import hash_password
from backend.infrastructure.db.repositories.user_repository import (
    SqlAlchemyUserRepository,
)


def seed_users():
    db_url = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/domain_copilot")
    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    repo = SqlAlchemyUserRepository(session=session)
    
    # Check if instructor exists
    if not repo.get_by_email("instructor@example.com"):
        print("Creating instructor...")
        instructor = User(
            user_id=str(uuid.uuid4()),
            email="instructor@example.com",
            hashed_password=hash_password("password123"),
            role=Role.INSTRUCTOR
        )
        repo.save(instructor)
    else:
        print("Instructor already exists.")
        
    # Check if lead instructor exists
    if not repo.get_by_email("lead@example.com"):
        print("Creating lead instructor...")
        lead = User(
            user_id=str(uuid.uuid4()),
            email="lead@example.com",
            hashed_password=hash_password("password123"),
            role=Role.LEAD_INSTRUCTOR
        )
        repo.save(lead)
    else:
        print("Lead instructor already exists.")
        
    print("Seed complete.")
    session.close()

if __name__ == "__main__":
    seed_users()
