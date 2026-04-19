"""Authentication schemas."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None
    role: UserRole = UserRole.VIEWER


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str | None
    role: UserRole
    is_active: bool
    created_at: datetime
    has_api_key: bool = False

    model_config = {"from_attributes": True}


class ApiKeyResponse(BaseModel):
    api_key: str
    message: str = "Store this key securely; it will not be shown again."
