import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.models.auth_session import AuthSession
from app.models.user_account import UserAccount

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


class AuthService:
    """Small account service with scrypt passwords and revocable DB sessions."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def register(self, username: str, password: str) -> tuple[UserAccount, str]:
        normalized = self._normalize_username(username)
        self._validate_password(password)
        if normalized == "legacy_local":
            raise AppError(
                ErrorCode.VALIDATION_ERROR, "该用户名不可用", status_code=422
            )
        existing = self.db.scalar(
            select(UserAccount).where(UserAccount.username == normalized)
        )
        if existing is not None:
            raise AppError(ErrorCode.VALIDATION_ERROR, "用户名已存在", status_code=409)
        now = datetime.now(timezone.utc)
        user = UserAccount(
            user_id=f"usr_{uuid4().hex}",
            username=normalized,
            password_hash=self.hash_password(password),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        self.db.add(user)
        self.db.flush()
        token = self._create_session(user.user_id, now)
        self.db.commit()
        self.db.refresh(user)
        return user, token

    def login(self, username: str, password: str) -> tuple[UserAccount, str]:
        normalized = self._normalize_username(username)
        self._validate_password(password)
        user = self.db.scalar(
            select(UserAccount).where(UserAccount.username == normalized)
        )
        if (
            user is None
            or not user.is_active
            or not self.verify_password(password, user.password_hash)
        ):
            raise AppError(
                ErrorCode.VALIDATION_ERROR, "用户名或密码错误", status_code=401
            )
        token = self._create_session(user.user_id, datetime.now(timezone.utc))
        self.db.commit()
        return user, token

    def authenticate(self, token: str) -> UserAccount:
        now = datetime.now(timezone.utc)
        session = self.db.scalar(
            select(AuthSession).where(
                AuthSession.token_hash == self._token_hash(token),
                AuthSession.expires_at > now,
            )
        )
        if session is None:
            raise AppError(
                ErrorCode.VALIDATION_ERROR, "登录已失效，请重新登录", status_code=401
            )
        user = self.db.get(UserAccount, session.user_id)
        if user is None or not user.is_active:
            raise AppError(ErrorCode.VALIDATION_ERROR, "账号不可用", status_code=401)
        if now - session.last_seen_at > timedelta(minutes=5):
            session.last_seen_at = now
            self.db.commit()
        return user

    def logout(self, token: str) -> None:
        session = self.db.scalar(
            select(AuthSession).where(AuthSession.token_hash == self._token_hash(token))
        )
        if session is not None:
            self.db.delete(session)
            self.db.commit()

    def _create_session(self, user_id: str, now: datetime) -> str:
        token = secrets.token_urlsafe(32)
        self.db.add(
            AuthSession(
                session_id=f"ses_{uuid4().hex}",
                token_hash=self._token_hash(token),
                user_id=user_id,
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(days=get_settings().auth_session_days),
            )
        )
        return token

    @staticmethod
    def hash_password(password: str) -> str:
        salt = secrets.token_bytes(16)
        derived = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P
        )
        return "scrypt${}${}${}${}${}".format(
            SCRYPT_N,
            SCRYPT_R,
            SCRYPT_P,
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(derived).decode("ascii"),
        )

    @staticmethod
    def verify_password(password: str, encoded: str) -> bool:
        try:
            algorithm, n, r, p, salt_text, digest_text = encoded.split("$", 5)
            if algorithm != "scrypt":
                return False
            salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
            expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
            actual = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt,
                n=int(n),
                r=int(r),
                p=int(p),
            )
            return hmac.compare_digest(actual, expected)
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_password(password: str) -> None:
        if not 8 <= len(password) <= 128:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "密码长度必须为 8 到 128 个字符",
                status_code=422,
            )

    @staticmethod
    def _normalize_username(username: str) -> str:
        normalized = username.strip().casefold()
        if not 3 <= len(normalized) <= 64:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "用户名长度必须为 3 到 64 个字符",
                status_code=422,
            )
        return normalized
