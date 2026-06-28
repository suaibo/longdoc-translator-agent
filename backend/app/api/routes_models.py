from typing import Any

from fastapi import APIRouter

from app.core.response import success
from app.services.model_catalog_service import ModelCatalogService

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("")
def list_models() -> dict[str, Any]:
    return success([option.to_dict() for option in ModelCatalogService().list_options()])
