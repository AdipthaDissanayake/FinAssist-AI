import json
import os
import secrets
import urllib.parse
import urllib.request
from urllib.error import HTTPError
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from .auth import create_access_token, get_current_user, hash_password, verify_password
from .database import get_database_session
from .models import User
from .subscription_service import create_free_subscription_if_missing

router = APIRouter(prefix="/auth", tags=["Authentication"])


# --- Pydantic Schemas ---
class UserRegisterRequest(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    password: str


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleLoginRequest(BaseModel):
    credential: str


class UserResponse(BaseModel):
    id: str
    first_name: str | None = None
    last_name: str | None = None
    email: str
    role: str
    auth_provider: str = "local"

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse | None = None


# --- Endpoints ---
@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: UserRegisterRequest, db: Session = Depends(get_database_session)):
    clean_email = user_data.email.strip().lower()
    existing_user = db.query(User).filter(User.email == clean_email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    try:
        new_user = User(
            first_name=user_data.first_name.strip() or None,
            last_name=user_data.last_name.strip() or None,
            email=clean_email,
            password_hash=hash_password(user_data.password),
            auth_provider="local",
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        create_free_subscription_if_missing(db, new_user.id)
        db.commit()
        access_token = create_access_token(
            data={"sub": new_user.id, "email": new_user.email, "role": new_user.role}
        )
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": new_user,
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration failed. Email may already be registered.",
        )


@router.post("/login", response_model=TokenResponse)
def login(credentials: UserLoginRequest, db: Session = Depends(get_database_session)):
    clean_email = credentials.email.strip().lower()
    user = db.query(User).filter(User.email == clean_email).first()
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    create_free_subscription_if_missing(db, user.id)
    db.commit()
    access_token = create_access_token(data={"sub": user.id, "email": user.email, "role": user.role})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user,
    }


@router.get("/google/client-id")
def google_client_id() -> dict[str, str]:
    """Expose the OAuth client ID required by Google Identity Services.

    A Google OAuth client ID is public configuration, unlike a client secret.
    """
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    return {"client_id": client_id}


@router.post("/google", response_model=TokenResponse)
def google_login(request: GoogleLoginRequest, db: Session = Depends(get_database_session)):
    claims = _verify_google_id_token(request.credential)
    google_sub = claims["sub"]
    email = claims["email"].strip().lower()
    given_name = claims.get("given_name") or ""
    family_name = claims.get("family_name") or ""
    if not given_name and not family_name:
        name_parts = (claims.get("name") or "").split(" ", 1)
        given_name = name_parts[0] if name_parts else ""
        family_name = name_parts[1] if len(name_parts) > 1 else ""

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
            if not user.first_name and given_name:
                user.first_name = given_name
            if not user.last_name and family_name:
                user.last_name = family_name
        else:
            user = User(
                first_name=given_name or None,
                last_name=family_name or None,
                email=email,
                google_sub=google_sub,
                auth_provider="google",
                password_hash=hash_password(secrets.token_urlsafe(32)),
            )
            db.add(user)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Could not create or link the Google account")
        db.refresh(user)

    create_free_subscription_if_missing(db, user.id)
    db.commit()
    access_token = create_access_token(data={"sub": user.id, "email": user.email, "role": user.role})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user,
    }


def _verify_google_id_token(id_token: str) -> dict[str, str]:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured",
        )

    clean_token = id_token.strip()
    if not clean_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Google credential",
        )

    url = f"https://oauth2.googleapis.com/tokeninfo?id_token={urllib.parse.quote(clean_token)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FinAssist-AI-Backend/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        error_msg = "Invalid Google token"
        try:
            err_json = json.loads(e.read().decode("utf-8"))
            if "error_description" in err_json:
                error_msg = err_json["error_description"]
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Google authentication failed: {error_msg}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not reach Google verification servers: {str(e)}",
        )

    # Validate audience matches client ID
    aud = data.get("aud")
    azp = data.get("azp")
    if aud != client_id and azp != client_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google sign-in token was issued for a different client ID",
        )

    # Validate email verification
    email_verified = data.get("email_verified")
    if str(email_verified).lower() not in ("true", "1"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google account email is not verified",
        )

    sub = data.get("sub")
    email = data.get("email")
    if not sub or not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google token missing user identity",
        )

    return {
        "sub": sub,
        "email": email,
        "given_name": data.get("given_name") or "",
        "family_name": data.get("family_name") or "",
        "name": data.get("name") or "",
    }


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
