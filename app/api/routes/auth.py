from fastapi import APIRouter, Depends, Header, Query, Request

from app.schemas.auth import (
    ChangePasswordRequest,
    ChangeRoleRequest,
    CurrentUserResponse,
    FreezeUserRequest,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    RegisterRequest,
    RegisterResponse,
    ReviewUserRequest,
    UpdateProfileRequest,
    UserListResponse,
    UserPublic,
)
from app.services.auth_service import (
    change_password,
    change_user_role,
    get_current_user,
    init_auth_storage,
    list_users,
    login_user,
    logout_token,
    register_user,
    require_admin,
    review_user,
    set_user_frozen,
    update_profile,
)


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse)
def register(request: RegisterRequest) -> RegisterResponse:
    user = register_user(
        login_account=request.login_account,
        password=request.password,
        username=request.username,
        register_reason=request.register_reason,
    )
    return RegisterResponse(user=UserPublic(**user), message="注册申请已提交，请等待管理员审核。")


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, http_request: Request) -> LoginResponse:
    result = login_user(
        login_account=request.login_account,
        password=request.password,
        user_agent=http_request.headers.get("user-agent", ""),
    )
    return LoginResponse(**result)


@router.post("/logout", response_model=MessageResponse)
def logout(authorization: str | None = Header(default=None)) -> MessageResponse:
    token = ""
    if authorization:
        token = authorization.split(" ", 1)[1].strip() if authorization.lower().startswith("bearer ") else authorization.strip()
    logout_token(token)
    return MessageResponse(message="已退出登录。")


@router.get("/me", response_model=CurrentUserResponse)
def current_user(current: dict = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse(user=UserPublic(**current))


@router.put("/me/profile", response_model=CurrentUserResponse)
def update_my_profile(request: UpdateProfileRequest, current: dict = Depends(get_current_user)) -> CurrentUserResponse:
    user = update_profile(str(current["id"]), request.username)
    return CurrentUserResponse(user=UserPublic(**user))


@router.put("/me/password", response_model=MessageResponse)
def update_my_password(request: ChangePasswordRequest, current: dict = Depends(get_current_user)) -> MessageResponse:
    change_password(str(current["id"]), request.old_password, request.new_password)
    return MessageResponse(message="密码已修改，请重新登录。")


@router.get("/admin/users", response_model=UserListResponse)
def admin_users(
    status: str | None = Query(default=None),
    query: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    _: dict = Depends(require_admin),
) -> UserListResponse:
    return UserListResponse(users=[UserPublic(**user) for user in list_users(status_filter=status, query=query, limit=limit)])


@router.post("/admin/users/{user_id}/review", response_model=CurrentUserResponse)
def admin_review_user(user_id: str, request: ReviewUserRequest, admin: dict = Depends(require_admin)) -> CurrentUserResponse:
    user = review_user(user_id=user_id, action=request.action, reason=request.reason, admin_user=admin)
    return CurrentUserResponse(user=UserPublic(**user))


@router.post("/admin/users/{user_id}/freeze", response_model=CurrentUserResponse)
def admin_freeze_user(user_id: str, request: FreezeUserRequest, admin: dict = Depends(require_admin)) -> CurrentUserResponse:
    user = set_user_frozen(user_id=user_id, frozen=request.frozen, reason=request.reason, admin_user=admin)
    return CurrentUserResponse(user=UserPublic(**user))


@router.post("/admin/users/{user_id}/role", response_model=CurrentUserResponse)
def admin_change_role(user_id: str, request: ChangeRoleRequest, admin: dict = Depends(require_admin)) -> CurrentUserResponse:
    user = change_user_role(user_id=user_id, role=request.role, admin_user=admin)
    return CurrentUserResponse(user=UserPublic(**user))


@router.post("/init", response_model=MessageResponse)
def init_auth() -> MessageResponse:
    init_auth_storage()
    return MessageResponse(message="认证数据库已初始化。")
