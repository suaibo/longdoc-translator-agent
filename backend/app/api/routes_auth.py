from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, bearer_token
from app.core.response import success
from app.db.session import get_db
from app.schemas.auth import AuthCredentials, AuthSessionResponse, AuthUserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _session_response(user, token: str) -> dict[str, Any]:
    return AuthSessionResponse(
        user_id=user.user_id, username=user.username, token=token
    ).model_dump(by_alias=True)


@router.post("/register")
def register(
    request: AuthCredentials,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    user, token = AuthService(db).register(request.username, request.password)
    return success(_session_response(user, token))


@router.post("/login")
def login(
    request: AuthCredentials,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    user, token = AuthService(db).login(request.username, request.password)
    return success(_session_response(user, token))


@router.post("/logout")
def logout(
    token: Annotated[str, Depends(bearer_token)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    AuthService(db).logout(token)
    return success({})


@router.get("/me")
def me(user: CurrentUser) -> dict[str, Any]:
    return success(
        AuthUserResponse(user_id=user.user_id, username=user.username).model_dump(
            by_alias=True
        )
    )
