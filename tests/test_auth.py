from fastapi.testclient import TestClient

from app.main import app


def test_login_com_credenciais_corretas_retorna_token():
    client = TestClient(app)
    response = client.post(
        "/auth/login", data={"username": "admin", "password": "admin123"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_com_senha_errada_retorna_401():
    client = TestClient(app)
    response = client.post(
        "/auth/login", data={"username": "admin", "password": "senha-errada"}
    )

    assert response.status_code == 401


def test_ingest_csv_sem_token_e_rejeitado():
    client = TestClient(app)
    response = client.post(
        "/ingest/csv",
        files={"file": ("teste.csv", b"id_sinistro\n1\n", "text/csv")},
    )

    assert response.status_code == 401


def test_ingest_csv_com_token_valido_e_aceito():
    client = TestClient(app)
    login = client.post(
        "/auth/login", data={"username": "admin", "password": "admin123"}
    )
    token = login.json()["access_token"]

    response = client.post(
        "/ingest/csv",
        files={
            "file": (
                "teste.csv",
                b"id_sinistro;municipio\n1;RIBEIRAO PRETO\n",
                "text/csv",
            )
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["inserted"] == 1


def test_register_cria_usuario_com_papel_user():
    client = TestClient(app)
    response = client.post(
        "/auth/register", json={"username": "novo_usuario", "password": "senha1234"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "novo_usuario"
    assert body["role"] == "user"
    assert "password" not in body and "password_hash" not in body


def test_register_com_username_duplicado_retorna_409():
    client = TestClient(app)
    client.post("/auth/register", json={"username": "duplicado", "password": "senha1234"})

    response = client.post(
        "/auth/register", json={"username": "duplicado", "password": "outrasenha"}
    )

    assert response.status_code == 409


def test_register_com_username_do_admin_raiz_retorna_409():
    client = TestClient(app)
    response = client.post(
        "/auth/register", json={"username": "admin", "password": "senha1234"}
    )

    assert response.status_code == 409


def test_usuario_cadastrado_consegue_logar():
    client = TestClient(app)
    client.post("/auth/register", json={"username": "usuario_login", "password": "senha1234"})

    response = client.post(
        "/auth/login", data={"username": "usuario_login", "password": "senha1234"}
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


def test_usuario_comum_nao_acessa_ingest_csv():
    client = TestClient(app)
    client.post("/auth/register", json={"username": "usuario_comum", "password": "senha1234"})
    login = client.post(
        "/auth/login", data={"username": "usuario_comum", "password": "senha1234"}
    )
    token = login.json()["access_token"]

    response = client.post(
        "/ingest/csv",
        files={"file": ("teste.csv", b"id_sinistro\n1\n", "text/csv")},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
