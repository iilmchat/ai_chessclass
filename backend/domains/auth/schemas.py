"""DTO домена auth: camelCase JSON (Design §12.1, SPEC.md §3)."""

from datetime import datetime

from pydantic import EmailStr, Field

from core.base import CamelModel
from domains.auth.models import User, UserRole


class RegisterIn(CamelModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(CamelModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class VerifyIn(CamelModel):
    token: str = Field(min_length=16, max_length=128)


class PasswordResetIn(CamelModel):
    email: EmailStr


class PasswordResetConfirmIn(CamelModel):
    token: str = Field(min_length=16, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)  # alias: newPassword


class UserOut(CamelModel):
    id: str
    email: EmailStr
    role: UserRole
    emailVerified: bool
    isActive: bool
    createdAt: datetime


class RegisterOut(CamelModel):
    id: str
    email: EmailStr
    role: UserRole
    emailVerified: bool


class AuthOut(CamelModel):
    accessToken: str
    tokenType: str = "Bearer"
    user: UserOut


class TokenOut(CamelModel):
    accessToken: str
    tokenType: str = "Bearer"


class MessageOut(CamelModel):
    ok: bool = True


def user_out(user: User) -> UserOut:
    """ORM → DTO (emailVerified вычисляется из email_verified_at)."""
    return UserOut(
        id=str(user.id),
        email=user.email,
        role=user.role,
        emailVerified=user.email_verified_at is not None,
        isActive=user.is_active,
        createdAt=user.created_at,
    )
