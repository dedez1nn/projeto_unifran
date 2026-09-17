from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import TokenData, create_access_token, hash_password, verify_password
from app.db.models import ROLE_ADMIN, ROLE_USER, User
from app.db.session import get_db
from app.schemas.auth import MeOut, Token, UserCreate, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, db: Session = Depends(get_db)) -> User:
    """Cadastro público de conta. Sempre cria a conta com papel `user` (o
    campo não é aceito na entrada, então não tem como um cadastro se
    autopromover a admin). Só o admin raiz, configurado via variáveis de
    ambiente (`ADMIN_USERNAME`/`ADMIN_PASSWORD_HASH`), pode importar CSVs.
    """
    username_em_uso = (
        user_in.username == settings.admin_username
        or db.query(User).filter(User.username == user_in.username).first() is not None
    )
    if username_em_uso:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nome de usuário já em uso",
        )

    user = User(
        username=user_in.username,
        password_hash=hash_password(user_in.password),
        role=ROLE_USER,
        name=user_in.name,
        email=user_in.email,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
) -> Token:
    """Autentica contra o admin raiz (variáveis de ambiente) ou, se não bater,
    contra a tabela `users` (contas de `POST /auth/register`). Retorna um
    token Bearer (JWT) com o papel (`admin`/`user`) embutido. Ver
    `core/security.py` e `api/deps.py` para como as rotas protegidas usam
    esse papel.
    """
    if form_data.username == settings.admin_username and verify_password(
        form_data.password, settings.admin_password_hash
    ):
        access_token = create_access_token(subject=form_data.username, role=ROLE_ADMIN)
        return Token(access_token=access_token)

    user = db.query(User).filter(User.username == form_data.username).first()
    if user is not None and verify_password(form_data.password, user.password_hash):
        access_token = create_access_token(subject=user.username, role=user.role)
        return Token(access_token=access_token)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Usuário ou senha inválidos",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.get("/me", response_model=MeOut)
async def me(
    token_data: TokenData = Depends(get_current_user), db: Session = Depends(get_db)
) -> MeOut:
    """Identidade do usuário do token atual, para o frontend montar a sessão
    (nome exibido, papel) sem precisar decodificar o JWT sozinho.
    """
    user = db.query(User).filter(User.username == token_data.username).first()
    return MeOut(
        username=token_data.username,
        role=token_data.role,
        name=user.name if user else None,
        email=user.email if user else None,
    )
