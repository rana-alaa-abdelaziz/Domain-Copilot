from dataclasses import dataclass
from enum import Enum


class Role(str, Enum):
    INSTRUCTOR = "instructor"
    LEAD_INSTRUCTOR = "lead_instructor"


@dataclass
class User:
    user_id: str
    email: str
    hashed_password: str
    role: Role
