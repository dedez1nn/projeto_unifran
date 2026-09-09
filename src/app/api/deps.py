from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.security import TokenData, decode_access_token
from app.db.models import ROLE_ADMIN

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenData:
    """Dependência que exige um Bearer token JWT válido (obtido em POST
    /auth/login) e devolve `(username, role)`. Qualquer conta autenticada
    passa aqui, admin raiz ou usuário cadastrado via POST /auth/register.
    """
    token_data = decode_access_token(token)
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_data


def get_current_admin(token_data: TokenData = Depends(get_current_user)) -> str:
    """Dependência que protege rotas de admin: exige, além de um token válido
    (ver `get_current_user`), que o papel embutido no token seja `admin`.
    Contas cadastradas via POST /auth/register nascem como `user` e não
    passam aqui (403). Devolve o username autenticado.
    """
    if token_data.role != ROLE_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores",
        )
    return token_data.username
