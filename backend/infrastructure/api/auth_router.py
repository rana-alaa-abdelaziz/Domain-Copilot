from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from backend.infrastructure.auth.jwt_handler import create_access_token
from backend.infrastructure.auth.password_hashing import verify_password
from backend.infrastructure.db.repositories.user_repository import (
    SqlAlchemyUserRepository,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

@router.post("/login", status_code=status.HTTP_200_OK)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """
    Authenticate user by email (username field) and password.
    Returns a JWT access token.
    """
    db_session = request.app.state.db_session
    user_repo = SqlAlchemyUserRepository(session=db_session)
    
    user = user_repo.get_by_email(form_data.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create token payload
    access_token = create_access_token(
        data={"sub": user.email, "role": user.role.value}
    )
    
    return {"access_token": access_token, "token_type": "bearer"}
