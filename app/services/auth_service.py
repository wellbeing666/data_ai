import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import Depends, Header, HTTPException, status

from app.core.database import init_database_schema, mysql_connection


TOKEN_TTL_DAYS = int(os.getenv("AUTH_TOKEN_TTL_DAYS", "7"))
PASSWORD_ITERATIONS = 180_000
DEFAULT_ADMIN_ACCOUNT = os.getenv("ADMIN_INITIAL_ACCOUNT", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("ADMIN_INITIAL_PASSWORD", "admin123456")
DEFAULT_ADMIN_USERNAME = os.getenv("ADMIN_INITIAL_USERNAME", "系统管理员")

USER_PUBLIC_FIELDS = (
    "id",
    "login_account",
    "username",
    "role",
    "status",
    "created_at",
    "updated_at",
    "approved_at",
    "last_login_at",
    "audit_reason",
)


class AuthError(RuntimeError):
    pass


def init_auth_storage() -> None:
    init_database_schema()
    with mysql_connection() as conn:
        _bootstrap_admin(conn)
        conn.commit()


def _now_db() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _now() -> str:
    return _serialize_datetime(_now_db())


def _utc_now() -> datetime:
    return _now_db()


def _serialize_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def _bootstrap_admin(conn) -> None:
    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
        row = cursor.fetchone()
        if row:
            return
        timestamp = _now_db()
        cursor.execute(
            """
            INSERT INTO users (
                id, login_account, username, role, password_hash, status,
                register_reason, audit_reason, approved_by, approved_at,
                created_at, updated_at, last_login_at
            ) VALUES (%s, %s, %s, 'admin', %s, 'active', %s, %s, NULL, %s, %s, %s, NULL)
            """,
            (
                uuid4().hex,
                _normalize_account(DEFAULT_ADMIN_ACCOUNT),
                DEFAULT_ADMIN_USERNAME,
                hash_password(DEFAULT_ADMIN_PASSWORD),
                "系统初始化默认管理员。",
                "系统自动创建默认管理员，请上线后立即修改密码。",
                timestamp,
                timestamp,
                timestamp,
            ),
        )


def hash_password(password: str) -> str:
    if not password or len(password) < 6:
        raise AuthError("密码长度不能少于 6 位。")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, iterations_text, salt, expected = password_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
        return hmac.compare_digest(digest.hex(), expected)
    except Exception:
        return False


def register_user(login_account: str, password: str, username: str, register_reason: str = "") -> dict[str, Any]:
    account = _normalize_account(login_account)
    display_name = _normalize_username(username)
    password_hash = hash_password(password)
    timestamp = _now_db()
    init_auth_storage()
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE login_account = %s", (account,))
            existing = cursor.fetchone()
            if existing:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="登录账号已存在，请更换账号或直接登录。")
            user_id = uuid4().hex
            cursor.execute(
                """
                INSERT INTO users (
                    id, login_account, username, role, password_hash, status,
                    register_reason, audit_reason, approved_by, approved_at,
                    created_at, updated_at, last_login_at
                ) VALUES (%s, %s, %s, 'user', %s, 'pending', %s, '', NULL, NULL, %s, %s, NULL)
                """,
                (user_id, account, display_name, password_hash, str(register_reason or "")[:500], timestamp, timestamp),
            )
        conn.commit()
        return _public_user(_get_user_by_id(conn, user_id))


def login_user(login_account: str, password: str, user_agent: str = "") -> dict[str, Any]:
    account = _normalize_account(login_account)
    init_auth_storage()
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE login_account = %s", (account,))
            row = cursor.fetchone()
            if row is None or not verify_password(password, str(row["password_hash"])):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码不正确。")
            if row["status"] == "pending":
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号仍在等待管理员审核。")
            if row["status"] == "frozen":
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被冻结，请联系管理员。")
            if row["status"] == "rejected":
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号注册申请未通过审核。")
            token = secrets.token_urlsafe(36)
            token_hash = _hash_token(token)
            created_at = _utc_now()
            expires_at = created_at + timedelta(days=max(1, TOKEN_TTL_DAYS))
            cursor.execute(
                "INSERT INTO auth_sessions (token_hash, user_id, created_at, expires_at, revoked_at, user_agent) VALUES (%s, %s, %s, %s, NULL, %s)",
                (token_hash, row["id"], created_at, expires_at, str(user_agent or "")[:300]),
            )
            timestamp = _now_db()
            cursor.execute("UPDATE users SET last_login_at = %s, updated_at = %s WHERE id = %s", (timestamp, timestamp, row["id"]))
        conn.commit()
        fresh = _get_user_by_id(conn, str(row["id"]))
        return {"token": token, "token_type": "Bearer", "expires_at": _serialize_datetime(expires_at) or "", "user": _public_user(fresh)}


def logout_token(token: str) -> None:
    if not token:
        return
    init_auth_storage()
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE auth_sessions SET revoked_at = %s WHERE token_hash = %s", (_now_db(), _hash_token(token)))
        conn.commit()


def get_user_from_token(token: str) -> dict[str, Any]:
    init_auth_storage()
    token_hash = _hash_token(token)
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT users.*
                FROM auth_sessions
                JOIN users ON users.id = auth_sessions.user_id
                WHERE auth_sessions.token_hash = %s
                  AND auth_sessions.revoked_at IS NULL
                  AND auth_sessions.expires_at > %s
                """,
                (token_hash, _now_db()),
            )
            row = cursor.fetchone()
            if row is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期，请重新登录。")
            if row["status"] != "active":
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号当前不可用，请联系管理员。")
            return _public_user(row)


def get_current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录。")
    return get_user_from_token(token)


def get_optional_current_user(authorization: str | None = Header(default=None)) -> dict[str, Any] | None:
    token = _extract_bearer_token(authorization)
    if not token:
        return None
    try:
        return get_user_from_token(token)
    except HTTPException:
        return None


def require_admin(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限。")
    return current_user


def update_profile(user_id: str, username: str) -> dict[str, Any]:
    display_name = _normalize_username(username)
    init_auth_storage()
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE users SET username = %s, updated_at = %s WHERE id = %s", (display_name, _now_db(), user_id))
        conn.commit()
        return _public_user(_get_user_by_id(conn, user_id))


def change_password(user_id: str, old_password: str, new_password: str) -> None:
    init_auth_storage()
    with mysql_connection() as conn:
        row = _get_user_by_id(conn, user_id)
        if row is None or not verify_password(old_password, str(row["password_hash"])):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码不正确。")
        with conn.cursor() as cursor:
            timestamp = _now_db()
            cursor.execute("UPDATE users SET password_hash = %s, updated_at = %s WHERE id = %s", (hash_password(new_password), timestamp, user_id))
            cursor.execute("UPDATE auth_sessions SET revoked_at = %s WHERE user_id = %s", (timestamp, user_id))
        conn.commit()


def list_users(status_filter: str | None = None, query: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    init_auth_storage()
    safe_limit = max(1, min(int(limit), 200))
    conditions: list[str] = []
    params: list[Any] = []
    if status_filter:
        conditions.append("status = %s")
        params.append(status_filter)
    if query and query.strip():
        conditions.append("(login_account LIKE %s OR username LIKE %s)")
        like = f"%{query.strip()}%"
        params.extend([like, like])
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM users {where_clause} ORDER BY created_at DESC LIMIT %s",
                (*params, safe_limit),
            )
            rows = cursor.fetchall()
            return [_public_user(row) for row in rows]


def review_user(user_id: str, action: str, reason: str, admin_user: dict[str, Any]) -> dict[str, Any]:
    normalized_action = str(action or "").strip()
    if normalized_action not in {"approve", "reject"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="审核动作必须是 approve 或 reject。")
    new_status = "active" if normalized_action == "approve" else "rejected"
    timestamp = _now_db()
    init_auth_storage()
    with mysql_connection() as conn:
        row = _get_user_by_id(conn, user_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在。")
        if row["role"] == "admin" and normalized_action == "reject":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="管理员账号不能被驳回。")
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE users
                SET status = %s, audit_reason = %s, approved_by = %s, approved_at = %s, updated_at = %s
                WHERE id = %s
                """,
                (new_status, str(reason or "")[:500], admin_user["id"], timestamp, timestamp, user_id),
            )
        conn.commit()
        return _public_user(_get_user_by_id(conn, user_id))


def set_user_frozen(user_id: str, frozen: bool, reason: str, admin_user: dict[str, Any]) -> dict[str, Any]:
    timestamp = _now_db()
    init_auth_storage()
    with mysql_connection() as conn:
        row = _get_user_by_id(conn, user_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在。")
        if row["role"] == "admin" and frozen:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="管理员账号不能被冻结。")
        new_status = "frozen" if frozen else "active"
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE users SET status = %s, audit_reason = %s, approved_by = %s, updated_at = %s WHERE id = %s",
                (new_status, str(reason or "")[:500], admin_user["id"], timestamp, user_id),
            )
            if frozen:
                cursor.execute("UPDATE auth_sessions SET revoked_at = %s WHERE user_id = %s", (timestamp, user_id))
        conn.commit()
        return _public_user(_get_user_by_id(conn, user_id))


def change_user_role(user_id: str, role: str, admin_user: dict[str, Any]) -> dict[str, Any]:
    normalized_role = str(role or "").strip()
    if normalized_role not in {"user", "admin"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="角色必须是 user 或 admin。")
    init_auth_storage()
    with mysql_connection() as conn:
        row = _get_user_by_id(conn, user_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在。")
        if row["id"] == admin_user.get("id") and normalized_role != "admin":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能取消自己的管理员角色。")
        with conn.cursor() as cursor:
            cursor.execute("UPDATE users SET role = %s, updated_at = %s WHERE id = %s", (normalized_role, _now_db(), user_id))
        conn.commit()
        return _public_user(_get_user_by_id(conn, user_id))


def _get_user_by_id(conn, user_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        return cursor.fetchone()


def _public_user(row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在。")
    result: dict[str, Any] = {}
    for key in USER_PUBLIC_FIELDS:
        if key in row:
            value = row[key]
            result[key] = _serialize_datetime(value) if isinstance(value, datetime) else value
    return result


def _normalize_account(account: str) -> str:
    normalized = str(account or "").strip().lower()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="登录账号不能为空。")
    if len(normalized) < 3 or len(normalized) > 40:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="登录账号长度需为 3-40 位。")
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789._-@")
    if any(char not in allowed for char in normalized):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="登录账号只能包含字母、数字、点、下划线、短横线或 @。")
    return normalized


def _normalize_username(username: str) -> str:
    normalized = str(username or "").strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名不能为空。")
    if len(normalized) > 50:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名不能超过 50 个字符。")
    return normalized


def _extract_bearer_token(authorization: str | None) -> str:
    value = str(authorization or "").strip()
    if not value:
        return ""
    if value.lower().startswith("bearer "):
        return value.split(" ", 1)[1].strip()
    return value


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
