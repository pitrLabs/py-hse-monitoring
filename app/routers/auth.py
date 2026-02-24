from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app import schemas
from app.auth import (authenticate_user, create_access_token, get_password_hash,
                      get_current_active_user, get_current_superuser, ACCESS_TOKEN_EXPIRE_MINUTES,
                      require_permission, generate_session_id)
from app.database import get_db
from app.models import User, Role
from app.services.audit_logger import log_audit
router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already registered")

    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    db_user = User(username=user_data.username, email=user_data.email, full_name=user_data.full_name,
                   hashed_password=get_password_hash(user_data.password))

    if user_data.role_ids:
        roles = db.query(Role).filter(Role.id.in_(user_data.role_ids)).all()
        db_user.roles = roles
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return db_user


@router.post("/login", response_model=schemas.Token)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    force: bool = False,
    db: Session = Depends(get_db)
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        # Check if user exists to provide more specific error
        existing_user = db.query(User).filter(User.username == form_data.username).first()
        if existing_user:
            error_detail = f"Invalid password for user '{form_data.username}'"
        else:
            error_detail = f"User '{form_data.username}' not found in system"

        # Log failed login attempt
        log_audit(
            db=db,
            user=None,
            action="user.login_failed",
            resource_type="user",
            resource_name=form_data.username,
            status="failed",
            error_message=error_detail,
            request=request
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Incorrect username or password",
                            headers={"WWW-Authenticate": "Bearer"})

    if not user.is_active:
        # Log inactive user login attempt
        log_audit(
            db=db,
            user=user,
            action="user.login_failed",
            resource_type="user",
            resource_id=user.id,
            resource_name=user.username,
            status="failed",
            error_message="User account is inactive",
            request=request
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Inactive user")

    # Check if user already has an active session elsewhere
    if user.active_session_id:
        # Check if session is expired (last_login_at + token_expiry < now)
        session_expired = False
        if user.last_login_at:
            session_expiry_time = user.last_login_at + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            if datetime.utcnow() > session_expiry_time:
                session_expired = True
                print(f"[Auth] Session expired for {user.username}, allowing new login")

        if not session_expired:
            # Session still valid - check if user is admin/superuser
            is_admin = user.is_superuser or any(
                role.name.lower() in ['manager', 'superadmin']
                for role in user.roles
            )

            # If force=true and user is admin, allow kicking old session
            if force and is_admin:
                pass  # Allow login, will overwrite session below
            else:
                # Return error with is_admin flag so frontend can show Force Login option
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "already_logged_in",
                        "is_admin": is_admin
                    }
                )

    # Generate new session ID
    session_id = generate_session_id()
    user.active_session_id = session_id
    user.last_login_at = datetime.utcnow()
    db.commit()

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires,
        session_id=session_id
    )

    # Log successful login
    log_audit(
        db=db,
        user=user,
        action="user.login",
        resource_type="user",
        resource_id=user.id,
        resource_name=user.username,
        new_values={"session_id": session_id},
        extra_metadata={"force_login": force},
        request=request
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout")
def logout(request: Request, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """Logout user by clearing active session ID"""
    current_user.active_session_id = None
    db.commit()

    # Log logout
    log_audit(
        db=db,
        user=current_user,
        action="user.logout",
        resource_type="user",
        resource_id=current_user.id,
        resource_name=current_user.username,
        request=request
    )

    return {"message": "Successfully logged out"}


@router.get("/me", response_model=schemas.UserResponse)
def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    return current_user


@router.put("/me", response_model=schemas.UserResponse)
def update_current_user(
    request: Request,
    user_update: schemas.UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Capture old values for audit
    old_values = {
        "email": current_user.email,
        "full_name": current_user.full_name
    }

    if user_update.email is not None:
        existing_user = db.query(User).filter(User.email == user_update.email,
                                              User.id != current_user.id).first()

        if existing_user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
        current_user.email = user_update.email

    if user_update.full_name is not None:
        current_user.full_name = user_update.full_name

    password_changed = False
    if user_update.password is not None:
        current_user.hashed_password = get_password_hash(user_update.password)
        password_changed = True

    db.commit()
    db.refresh(current_user)

    # Capture new values
    new_values = {
        "email": current_user.email,
        "full_name": current_user.full_name,
        "password_changed": password_changed
    }

    # Log profile update
    log_audit(
        db=db,
        user=current_user,
        action="user.profile_updated",
        resource_type="user",
        resource_id=current_user.id,
        resource_name=current_user.username,
        old_values=old_values,
        new_values=new_values,
        request=request
    )

    return current_user
