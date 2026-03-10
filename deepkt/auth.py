"""
Auth — JWT tokens, password hashing, OAuth helpers, and FastAPI dependencies.
"""

import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Optional

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request

from deepkt import user_db

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRY = timedelta(minutes=15)
REFRESH_TOKEN_EXPIRY = timedelta(days=30)

_ph = PasswordHasher()


# ---------------------------------------------------------------------------
# Password hashing (argon2)
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plain)
    except VerifyMismatchError:
        return False


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------

@dataclass
class UserClaims:
    user_id: str
    email: str


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "type": "access",
        "exp": datetime.now(timezone.utc) + ACCESS_TOKEN_EXPIRY,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> tuple[str, str]:
    """Create a refresh token. Returns (raw_token, hashed_jti) for DB storage."""
    jti = uuid.uuid4().hex
    payload = {
        "sub": user_id,
        "type": "refresh",
        "jti": jti,
        "exp": datetime.now(timezone.utc) + REFRESH_TOKEN_EXPIRY,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    hashed_jti = hashlib.sha256(jti.encode()).hexdigest()
    return token, hashed_jti


def decode_token(token: str) -> dict:
    """Decode and verify a JWT. Raises jwt.PyJWTError on failure."""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

def _extract_bearer(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def get_current_user(request: Request) -> UserClaims:
    """FastAPI Depends — extracts Bearer token, returns UserClaims or raises 401."""
    token = _extract_bearer(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return UserClaims(user_id=payload["sub"], email=payload["email"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def optional_current_user(request: Request) -> Optional[UserClaims]:
    """Same as get_current_user but returns None instead of 401."""
    token = _extract_bearer(request)
    if not token:
        return None
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        return UserClaims(user_id=payload["sub"], email=payload["email"])
    except jwt.PyJWTError:
        return None


# ---------------------------------------------------------------------------
# User DB helpers (delegated to user_db — PostgreSQL in prod, SQLite locally)
# ---------------------------------------------------------------------------

def create_user(email: str, display_name: str = None, password: str = None,
                auth_provider: str = "email", provider_id: str = None) -> dict:
    """Create a new user. Returns the user dict."""
    password_hash = hash_password(password) if password else None
    return user_db.create_user(
        email=email, display_name=display_name, password_hash=password_hash,
        auth_provider=auth_provider, provider_id=provider_id,
    )


def get_user_by_email(email: str) -> Optional[dict]:
    return user_db.get_user_by_email(email)


def get_user_by_provider(provider: str, provider_id: str) -> Optional[dict]:
    return user_db.get_user_by_provider(provider, provider_id)


def get_user_by_id(user_id: str) -> Optional[dict]:
    return user_db.get_user_by_id(user_id)


def store_refresh_token(user_id: str, hashed_jti: str):
    """Store the hashed refresh token jti for the user (single-session: replaces old)."""
    user_db.store_refresh_token(user_id, hashed_jti)


def revoke_refresh_token(user_id: str):
    """Revoke the user's refresh token."""
    user_db.revoke_refresh_token(user_id)


def link_oauth_provider(user_id: str, provider: str, provider_id: str):
    """Link an OAuth provider to an existing user."""
    user_db.link_oauth_provider(user_id, provider, provider_id)


# ---------------------------------------------------------------------------
# Google OAuth helpers
# ---------------------------------------------------------------------------

async def google_oauth_exchange(code: str) -> dict:
    """Exchange Google auth code for user info. Returns {email, name, provider_id}."""
    from authlib.integrations.httpx_client import AsyncOAuth2Client

    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/google/callback")

    client = AsyncOAuth2Client(client_id=client_id, client_secret=client_secret)
    token = await client.fetch_token(
        "https://oauth2.googleapis.com/token",
        code=code,
        redirect_uri=redirect_uri,
    )

    # Decode the ID token
    id_token = token.get("id_token")
    if not id_token:
        raise ValueError("No id_token in Google response")

    # Verify with Google's JWKS
    from authlib.jose import jwt as jose_jwt
    from authlib.jose import JsonWebKey
    import httpx

    async with httpx.AsyncClient() as http:
        resp = await http.get("https://www.googleapis.com/oauth2/v3/certs")
        jwks = resp.json()

    key_set = JsonWebKey.import_key_set(jwks)
    claims = jose_jwt.decode(id_token, key_set)
    claims.validate()

    return {
        "email": claims["email"],
        "name": claims.get("name", ""),
        "provider_id": claims["sub"],
    }
