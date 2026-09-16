from sqlalchemy.orm import Session

from backend.domain.entities.user import Role, User
from backend.domain.ports.user_repository import UserRepository
from backend.infrastructure.db.models import UserModel


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session: Session):
        self._session = session

    def get_by_email(self, email: str) -> User | None:
        model = self._session.query(UserModel).filter(UserModel.email == email).first()
        if not model:
            return None
        return self._to_entity(model)

    def get_by_id(self, user_id: str) -> User | None:
        model = (
            self._session.query(UserModel)
            .filter(UserModel.user_id == user_id)
            .first()
        )
        if not model:
            return None
        return self._to_entity(model)

    def save(self, user: User) -> None:
        model = (
            self._session.query(UserModel)
            .filter(UserModel.user_id == user.user_id)
            .first()
        )
        if not model:
            model = UserModel(
                user_id=user.user_id,
                email=user.email,
                hashed_password=user.hashed_password,
                role=user.role.value,
            )
            self._session.add(model)
        else:
            model.email = user.email
            model.hashed_password = user.hashed_password
            model.role = user.role.value
        
        self._session.commit()

    def _to_entity(self, model: UserModel) -> User:
        return User(
            user_id=model.user_id,
            email=model.email,
            hashed_password=model.hashed_password,
            role=Role(model.role),
        )
