import json
import os
import secrets
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from .auth import create_access_token, get_current_user, hash_password, verify_password
from .database import get_database_session
from .models import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


# --- Pydantic Schemas ---
class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleLoginRequest(BaseModel):
    credential: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: str
    role: str

    class Config:
        from_attributes = True


# --- Endpoints ---
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: UserRegisterRequest, db: Session = Depends(get_database_session)):
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    new_user = User(
        email=user_data.email,
        password_hash=hash_password(user_data.password),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.post("/login", response_model=TokenResponse)
def login(credentials: UserLoginRequest, db: Session = Depends(get_database_session)):
    user = db.query(User).filter(User.email == credentials.email).first()
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token(data={"sub": user.id, "email": user.email, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/google/client-id")
def google_client_id() -> dict[str, str]:
    """Expose the OAuth client ID required by Google Identity Services.

    A Google OAuth client ID is public configuration, unlike a client secret.
    """
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Google sign-in is not configured")
    return {"client_id": client_id}


@router.post("/google", response_model=TokenResponse)
def google_login(request: GoogleLoginRequest, db: Session = Depends(get_database_session)):
    claims = _verify_google_id_token(request.credential)
    google_sub = claims["sub"]
    email = claims["email"]

    # Provider ID is authoritative. It remains stable if a Google user later
    # changes their email address.
    user = db.query(User).filter(User.google_sub == google_sub).first()
    if user is None:
        # A verified Google email can safely attach to a pre-existing
        # email/password account, avoiding a duplicate account for one person.
        user = db.query(User).filter(User.email == email).first()
        if user is not None:
            if user.google_sub and user.google_sub != google_sub:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This email is already linked to another Google account")
            user.google_sub = google_sub
        else:
            # Keep password_hash non-null for compatibility with the existing
            # model; this randomly generated value is never disclosed.
            user = User(email=email, google_sub=google_sub, password_hash=hash_password(secrets.token_urlsafe(32)))
            db.add(user)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Could not create or link the Google account")
        db.refresh(user)

    access_token = create_access_token(data={"sub": user.id, "email": user.email, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer"}


def _verify_google_id_token(id_token: str) -> dict[str, str]:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Google sign-in is not configured")

    verifier = Path(__file__).with_name("google_token_verifier.mjs")
    try:
        completed = subprocess.run(
            ["node", str(verifier), client_id],
            input=id_token,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        claims = json.loads(completed.stdout) if completed.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        claims = None

    if not isinstance(claims, dict) or not isinstance(claims.get("sub"), str) or not isinstance(claims.get("email"), str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google sign-in token")
    return claims


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
