import datetime as dt

from fastapi.testclient import TestClient

from app.db.models import Sinistro
from app.db.session import Base, SessionLocal, engine
from app.main import app


def setup_module() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.add_all(
            [
                Sinistro(
                    source_name="teste_sinistros",
                    source_row_id="1",
                    municipio="RIBEIRAO PRETO",
                    data_sinistro=dt.date(2024, 1, 10),
                    ano_sinistro=2024,
                    latitude=-21.1775,
                    longitude=-47.8103,
                    logradouro="Rua Dentro Da Bbox",
                    tipo_via="Avenida",
                    regiao_administrativa="Central",
                    qtd_gravidade_fatal=1,
                    qtd_gravidade_leve=0,
                ),
                Sinistro(
                    source_name="teste_sinistros",
                    source_row_id="2",
                    municipio="RIBEIRAO PRETO",
                    data_sinistro=dt.date(2024, 2, 15),
                    latitude=-21.5,
                    longitude=-48.2,
                    logradouro="Rua Fora Da Bbox",
                    tipo_via="Rua",
                    regiao_administrativa="Norte",
                    qtd_gravidade_fatal=0,
                    qtd_gravidade_leve=1,
                ),
                Sinistro(
                    source_name="teste_sinistros",
                    source_row_id="3",
                    municipio="RIBEIRAO PRETO",
                    data_sinistro=dt.date(2024, 3, 1),
                    latitude=None,
                    longitude=None,
                    logradouro="Sem Coordenadas",
                ),
            ]
        )
        db.commit()
    finally:
        db.close()


def test_geojson_retorna_feature_collection_so_com_pontos_geocodificados():
    client = TestClient(app)
    response = client.get("/sinistros/geojson")

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    logradouros = {f["properties"]["logradouro"] for f in body["features"]}
    assert "Sem Coordenadas" not in logradouros

    feature = next(
        f for f in body["features"] if f["properties"]["logradouro"] == "Rua Dentro Da Bbox"
    )
    assert feature["type"] == "Feature"
    assert feature["geometry"] == {
        "type": "Point",
        "coordinates": [-47.8103, -21.1775],
    }


def test_geojson_filtra_por_bbox():
    client = TestClient(app)
    response = client.get(
        "/sinistros/geojson",
        params={"lat_min": -21.3, "lat_max": -21.0, "lon_min": -48.0, "lon_max": -47.5},
    )

    assert response.status_code == 200
    logradouros = {f["properties"]["logradouro"] for f in response.json()["features"]}
    assert "Rua Dentro Da Bbox" in logradouros
    assert "Rua Fora Da Bbox" not in logradouros


def test_geojson_filtra_por_gravidade():
    client = TestClient(app)
    response = client.get("/sinistros/geojson", params={"gravidade": "fatal"})

    assert response.status_code == 200
    logradouros = {f["properties"]["logradouro"] for f in response.json()["features"]}
    assert logradouros == {"Rua Dentro Da Bbox"}


def test_geojson_gravidade_invalida_retorna_400():
    client = TestClient(app)
    response = client.get("/sinistros/geojson", params={"gravidade": "inexistente"})

    assert response.status_code == 400


def test_list_sinistros_filtra_por_regiao_administrativa():
    client = TestClient(app)
    response = client.get("/sinistros", params={"regiao_administrativa": "Norte"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["logradouro"] == "Rua Fora Da Bbox"


def test_list_sinistros_filtra_por_bbox():
    client = TestClient(app)
    response = client.get(
        "/sinistros",
        params={"lat_min": -21.3, "lat_max": -21.0, "lon_min": -48.0, "lon_max": -47.5},
    )

    assert response.status_code == 200
    logradouros = {r["logradouro"] for r in response.json()}
    assert "Rua Dentro Da Bbox" in logradouros
    assert "Rua Fora Da Bbox" not in logradouros


def test_opcoes_retorna_valores_distintos_presentes_na_base():
    client = TestClient(app)
    response = client.get("/sinistros/opcoes")

    assert response.status_code == 200
    body = response.json()
    assert "Avenida" in body["tipo_via"]
    assert "Rua" in body["tipo_via"]
    assert {"Central", "Norte"} <= set(body["regiao_administrativa"])
    assert 2024 in body["anos"]
    assert body["gravidade"] == ["fatal", "grave", "ileso", "leve"]
    # sem duplicatas: "Avenida" aparece em mais de um registro na base
    assert len(body["tipo_via"]) == len(set(body["tipo_via"]))
