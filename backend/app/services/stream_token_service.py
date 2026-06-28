import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode


class StreamTokenService:
    def issue(self, user_id: str, job_id: str) -> str:
        settings = get_settings()
        payload = {
            "userId": user_id,
            "jobId": job_id,
            "exp": int(time.time()) + settings.stream_token_ttl_seconds,
        }
        body = self._b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signature = self._sign(body)
        return f"{body}.{signature}"

    def verify(self, token: str, job_id: str) -> dict[str, Any]:
        try:
            body, signature = token.split(".", 1)
        except ValueError as exc:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "事件流 token 无效",
                status_code=401,
            ) from exc
        if not hmac.compare_digest(signature, self._sign(body)):
            raise AppError(ErrorCode.VALIDATION_ERROR, "事件流 token 无效", status_code=401)
        try:
            payload = json.loads(self._unb64(body).decode("utf-8"))
        except (ValueError, TypeError) as exc:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "事件流 token 无效",
                status_code=401,
            ) from exc
        if payload.get("jobId") != job_id or int(payload.get("exp") or 0) < time.time():
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "事件流 token 已过期或不匹配",
                status_code=401,
            )
        return payload

    def _sign(self, body: str) -> str:
        return self._b64(
            hmac.new(self._secret(), body.encode("ascii"), hashlib.sha256).digest()
        )

    @staticmethod
    def _secret() -> bytes:
        settings = get_settings()
        raw = settings.stream_token_secret or f"{settings.database_url}:{settings.app_env}"
        return hashlib.sha256(raw.encode("utf-8")).digest()

    @staticmethod
    def _b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _unb64(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode((value + padding).encode("ascii"))
