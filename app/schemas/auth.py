from typing import Any

from pydantic import BaseModel, Field


class UserPublic(BaseModel):
    id: str
    login_account: str
    username: str
    role: str
    status: str
    created_at: str | None = None
    updated_at: str | None = None
    approved_at: str | None = None
    last_login_at: str | None = None
    audit_reason: str | None = None


class RegisterRequest(BaseModel):
    login_account: str = Field(..., min_length=3, max_length=40)
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=6, max_length=128)
    register_reason: str = Field(default="", max_length=500)


class LoginRequest(BaseModel):
    login_account: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=128)


class LoginResponse(BaseModel):
    token: str
    token_type: str = "Bearer"
    expires_at: str
    user: UserPublic


class RegisterResponse(BaseModel):
    user: UserPublic
    message: str


class CurrentUserResponse(BaseModel):
    user: UserPublic


class UpdateProfileRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=6, max_length=128)


class UserListResponse(BaseModel):
    users: list[UserPublic]


class ReviewUserRequest(BaseModel):
    action: str = Field(..., min_length=1)
    reason: str = Field(default="", max_length=500)


class FreezeUserRequest(BaseModel):
    frozen: bool
    reason: str = Field(default="", max_length=500)


class ChangeRoleRequest(BaseModel):
    role: str = Field(..., min_length=1)


class MessageResponse(BaseModel):
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
