from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def sync_missing_columns() -> None:
    """Remendo mínimo de schema: `Base.metadata.create_all` só cria tabelas
    que ainda não existem, nunca adiciona coluna em tabela já existente. Sem
    Alembic no projeto (ver README, "Próximos passos"), quem já tinha o
    banco criado antes de um model ganhar uma coluna nova (ex.: `name`/
    `email` em `User`) quebra em runtime com `no such column`. Isto cobre só
    esse caso — coluna nova e opcional — não lida com renomear/remover
    coluna nem mudar tipo, o que exigiria uma migração de verdade.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # tabela nova: create_all já criou com todas as colunas
            existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue
                ddl_type = column.type.compile(dialect=engine.dialect)
                conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {ddl_type}"))
