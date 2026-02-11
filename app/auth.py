import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Permission
from app.schemas import TokenData
from app.config import settings

SECRET_KEY = settings.secret_key
ALGORITHM = settings.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes

pwd_context = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def generate_session_id() -> str:
    """Generate a unique session ID for single-session enforcement"""
    return secrets.token_hex(32)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    valid = pwd_context.verify(plain_password, hashed_password)

    if valid and pwd_context.needs_update(hashed_password):
        new_hash = pwd_context.hash(plain_password)
        # user.hashed_password = new_hash
        # db.commit()

    return valid


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None, session_id: Optional[str] = None) -> str:
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)

    to_encode.update({"exp": expire})

    # Include session_id in token for single-session enforcement
    if session_id:
        to_encode.update({"sid": session_id})

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    return encoded_jwt


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.username == username).first()

    if not user:
        return None

    if not verify_password(password, user.hashed_password):
        return None

    return user


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                          detail="Could not validate credentials",
                                          headers={"WWW-Authenticate": "Bearer"})

    # Exception for session invalidation - logged in from another device
    session_another_device_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="session_invalid_another_device",
        headers={"WWW-Authenticate": "Bearer"}
    )

    # Exception for session invalidation - force logged out by admin
    session_force_logout_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="session_invalid_force_logout",
        headers={"WWW-Authenticate": "Bearer"}
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        session_id: str = payload.get("sid")  # Session ID from token

        if username is None:
            raise credentials_exception

        token_data = TokenData(username=username)

    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.username == token_data.username).first()

    if user is None:
        raise credentials_exception

    # Validate session_id - check if session is still valid
    if session_id:
        if not user.active_session_id:
            # Database has no active session = force logged out by admin
            raise session_force_logout_exception
        elif session_id != user.active_session_id:
            # Session IDs don't match = logged in from another device
            raise session_another_device_exception

    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    return current_user


async def get_current_superuser(current_user: User = Depends(get_current_active_user)) -> User:
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough privileges")

    return current_user


def check_user_permission(user: User, resource: str, action: str) -> bool:
    if user.is_superuser:
        return True

    for role in user.roles:
        for permission in role.permissions:
            if permission.resource == resource and permission.action == action:
                return True
    
    return False


def require_permission(resource: str, action: str):
    async def permission_checker(current_user: User = Depends(get_current_active_user)) -> User:
        if not check_user_permission(current_user, resource, action):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"Permission denied: {resource}.{action}")

        return current_user
    return permission_checker



def _prehash_password(password: str) -> bytes:
    return hashlib.sha256(password.encode("utf-8")).digest()
