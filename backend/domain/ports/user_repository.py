from abc import ABC, abstractmethod

from backend.domain.entities.user import User


class UserRepository(ABC):
    @abstractmethod
    def get_by_email(self, email: str) -> User | None:
        """Retrieve a user by email."""

    @abstractmethod
    def get_by_id(self, user_id: str) -> User | None:
        """Retrieve a user by ID."""

    @abstractmethod
    def save(self, user: User) -> None:
        """Save a new user."""
