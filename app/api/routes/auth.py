"""Authentication: register, login, JWT, API keys."""

import secrets

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.core.deps import CurrentUser, DbSession, OperatorUser
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User, UserRole
from app.models.voice import UsageAction
from app.schemas.auth import ApiKeyResponse, LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services.usage_tracker import UsageTracker

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: DbSession) -> UserResponse:
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    count_res = await db.execute(select(func.count()).select_from(User))
    total = int(count_res.scalar_one() or 0)
    role = UserRole.ADMIN if total == 0 else UserRole.VIEWER

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=role,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        has_api_key=bool(user.api_key),
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: DbSession) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    token = create_access_token(user.id)
    await UsageTracker(db).record_usage(user.id, UsageAction.API_CALL)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        has_api_key=bool(user.api_key),
    )


@router.post("/api-key", response_model=ApiKeyResponse)
async def generate_api_key(user: OperatorUser, db: DbSession) -> ApiKeyResponse:
    from app.core.config import settings

    key = f"{settings.API_KEY_PREFIX}{secrets.token_urlsafe(32)}"
    user.api_key = key
    await db.flush()
    return ApiKeyResponse(api_key=key)
