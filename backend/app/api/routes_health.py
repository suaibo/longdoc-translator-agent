from fastapi import APIRouter

from app.core.response import success

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health() -> dict[str, object]:
    return success(
        {
            "status": "UP",
            "service": "longdoc-translator-agent",
        }
    )
