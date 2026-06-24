from pydantic import BaseModel, ConfigDict

from app.schemas.job import to_camel


class OutputItem(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    type: str
    filename: str
    media_type: str
    available: bool
