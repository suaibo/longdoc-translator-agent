from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.db.session import get_db
from app.models.user_account import UserAccount
from app.services.auth_service import AuthService


def bearer_token(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError(ErrorCode.VALIDATION_ERROR, "请先登录", status_code=401)
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise AppError(ErrorCode.VALIDATION_ERROR, "请先登录", status_code=401)
    return token


def current_user(
    token: Annotated[str, Depends(bearer_token)],
    db: Annotated[Session, Depends(get_db)],
) -> UserAccount:
    return AuthService(db).authenticate(token)


CurrentUser = Annotated[UserAccount, Depends(current_user)]
