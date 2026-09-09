"""Autenticação: hash de senha (bcrypt) e tokens de acesso (JWT).

Existe um admin "raiz" fixo via variáveis de ambiente (`settings`, ver
`core/config.py`) mais uma tabela `users` (`db/models.py`) alimentada por
`POST /auth/register`, contas registradas por lá sempre nascem com papel
`user`; só o admin raiz carrega o papel `admin`. O token JWT carrega esse
papel (claim `role`) para as rotas protegidas decidirem autorização sem
precisar consultar o banco de novo (`api/deps.get_current_admin`).
"""

import datetime as dt
from typing import NamedTuple

import bcrypt
import jwt

from app.core.config import settings

TOKEN_SUBJECT_CLAIM = "sub"
TOKEN_ROLE_CLAIM = "role"


class TokenData(NamedTuple):
    username: str
    role: str


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(subject: str, role: str) -> str:
    expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {TOKEN_SUBJECT_CLAIM: subject, TOKEN_ROLE_CLAIM: role, "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenData | None:
    """Retorna `(username, role)` do token se válido, ou None (assinatura/expiração
    inválida). Tokens emitidos antes do claim `role` existir não têm mais como
    ser aceitos (sem papel, não dá pra autorizar); expiram naturalmente em até
    `ACCESS_TOKEN_EXPIRE_MINUTES`.
    """
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError:
        return None
    username = payload.get(TOKEN_SUBJECT_CLAIM)
    role = payload.get(TOKEN_ROLE_CLAIM)
    if not username or not role:
        return None
    return TokenData(username=username, role=role)
