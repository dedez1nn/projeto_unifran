import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=8, max_length=72)
    name: str | None = Field(default=None, max_length=150)
    email: str | None = Field(default=None, max_length=255)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    name: str | None
    email: str | None
    created_at: dt.datetime


class MeOut(BaseModel):
    """Identidade do usuário autenticado (`GET /auth/me`). O admin raiz não
    tem linha na tabela `users` (vem de `settings`), então `name`/`email`
    saem `None` para ele.
    """

    username: str
    role: str
    name: str | None
    email: str | None
