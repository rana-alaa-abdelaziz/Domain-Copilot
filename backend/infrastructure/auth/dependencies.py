from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.domain.entities.user import User
from backend.infrastructure.auth.jwt_handler import decode_access_token
from backend.infrastructure.db.repositories.user_repository import (
    SqlAlchemyUserRepository,
)

bearer_scheme = HTTPBearer()

def get_db(request: Request):
    """Retrieves the global DB session bound to app state."""
    return request.app.state.db_session

def get_current_user(
    token: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    session = Depends(get_db),
) -> User:
    """
    Extracts the user from the JWT token.
    Raises 401 if invalid, expired, or user not found.
    """
    payload = decode_access_token(token.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    email: str = payload.get("sub")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_repo = SqlAlchemyUserRepository(session=session)
    user = user_repo.get_by_email(email)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


def require_role(*allowed_roles: str) -> Callable:
    """
    Returns a dependency that checks if the current user has one of the allowed roles.
    Raises 403 Forbidden if not.
    """
    def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role.value not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )
        return current_user
    return role_checker
