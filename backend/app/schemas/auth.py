from pydantic import BaseModel, ConfigDict, Field

from app.schemas.job import to_camel


class AuthCredentials(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class AuthUserResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    user_id: str
    username: str


class AuthSessionResponse(AuthUserResponse):
    token: str
