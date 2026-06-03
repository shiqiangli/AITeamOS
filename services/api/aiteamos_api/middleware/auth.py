"""
API Gateway — Authentication Middleware (plan.md §1.5.4, §1.5.5).

PRD §2.9 极简权限模型:
- Admin（最高权限）: 通过环境变量 AITEAMOS_ADMIN_API_KEY 认证
- Employee: 后续可扩展 JWT / OAuth（当前阶段所有 API 均为 Admin-only）
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Request, status


@dataclass(frozen=True)
class AuthContext:
    """认证上下文。"""

    role: str  # "admin" | "employee"
    employee_id: Optional[str] = None


async def get_current_user(request: Request) -> AuthContext:
    """FastAPI 依赖：验证 Bearer Token。

    - 开发模式（AITEAMOS_ADMIN_API_KEY 未设置）：放行所有请求
    - Admin: token == os.environ["AITEAMOS_ADMIN_API_KEY"]
    - 未匹配时返回 401
    """
    admin_key = os.environ.get("AITEAMOS_ADMIN_API_KEY", "")

    # 开发模式：未配置密钥时放行
    if not admin_key:
        return AuthContext(role="admin", employee_id=None)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.removeprefix("Bearer ").strip()

    if hmac.compare_digest(token, admin_key):
        return AuthContext(role="admin", employee_id=None)

    # 后续可扩展 JWT / OAuth 用于 Employee 级认证
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
        headers={"WWW-Authenticate": "Bearer"},
    )


# Alias for route dependency injection
require_admin = Depends(get_current_user)
