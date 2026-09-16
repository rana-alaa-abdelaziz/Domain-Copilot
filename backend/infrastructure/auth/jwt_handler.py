from datetime import datetime, timedelta, timezone

import jwt

from backend.infrastructure.config import get_settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24


def create_access_token(data: dict) -> str:
    """Creates a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    
    settings = get_settings()
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict | None:
    """Decodes a JWT token. Returns payload dict or None if invalid/expired."""
    settings = get_settings()
    try:
        decoded_token = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return decoded_token
    except jwt.PyJWTError:
        return None
