import sqlite3

from sqlalchemy import create_engine, text

import app.db.session as db_session


def test_sync_missing_columns_adiciona_colunas_sem_perder_dados(tmp_path, monkeypatch):
    """Simula um banco criado antes de `name`/`email` existirem em `User`
    (exatamente o schema antigo que quebrava `POST /auth/register` com
    `no such column: users.name`) e confere que `sync_missing_columns`
    adiciona as colunas que faltam sem apagar as linhas já existentes.
    """
    db_path = tmp_path / "legacy.db"
    con = sqlite3.connect(db_path)
    con.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(150), "
        "password_hash VARCHAR(255), role VARCHAR(20), created_at DATETIME)"
    )
    con.execute(
        "INSERT INTO users (id, username, password_hash, role) VALUES (1, 'legado', 'hash', 'user')"
    )
    con.commit()
    con.close()

    engine = create_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(db_session, "engine", engine)

    db_session.sync_missing_columns()

    with engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(users)"))}
        assert {"name", "email"} <= columns

        row = conn.execute(text("SELECT username, role FROM users WHERE id = 1")).fetchone()
        assert row == ("legado", "user")


def test_sync_missing_columns_e_idempotente(tmp_path, monkeypatch):
    """Rodar de novo num banco já atualizado não pode falhar tentando
    adicionar uma coluna que já existe.
    """
    db_path = tmp_path / "up_to_date.db"
    engine = create_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(db_session, "engine", engine)
    db_session.Base.metadata.create_all(bind=engine)

    db_session.sync_missing_columns()
    db_session.sync_missing_columns()
