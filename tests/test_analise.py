"""Rotas `/analise/...` sobre um recorte próprio (ano 2031, `RUA ANALISE`),
removido no fim para não afetar as contagens dos outros testes."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.db.models import IndicadorMunicipio, Pessoa, Sinistro
from app.db.session import Base, SessionLocal, engine
from app.main import app

FONTE = "teste_analise"
VIA = "RUA ANALISE"
PERIODO = {"data_inicio": "2031-01-01", "data_fim": "2031-12-31"}


def _sinistro(n, data, hora, **campos):
    return Sinistro(source_name=FONTE, source_row_id=str(n), id_sinistro=9_100_000 + n, logradouro=VIA,
                    municipio="RIBEIRAO PRETO", data_sinistro=data, ano_sinistro=data.year, mes_sinistro=data.month,
                    hora_sinistro=hora, dia_da_semana="Segunda-feira", turno="MANHA", tipo_via="VIAS URBANAS",
                    tipo_registro=campos.pop("tipo_registro", "SINISTRO NAO FATAL"), **campos)


@pytest.fixture(scope="module", autouse=True)
def recorte():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    segunda = dt.date(2031, 3, 3)  # segunda-feira
    db.add_all([
        _sinistro(1, segunda, dt.time(7, 10), latitude=-21.17, longitude=-47.81, qtd_gravidade_fatal=1,
                  qtd_motocicleta=1, qtd_automovel=1, tipo_registro="SINISTRO FATAL", tp_sinistro_primario="COLISAO"),
        _sinistro(2, segunda, dt.time(7, 40), latitude=-21.171, longitude=-47.811, qtd_gravidade_grave=1,
                  qtd_automovel=1, tp_sinistro_primario="COLISAO"),
        _sinistro(3, dt.date(2031, 4, 9), dt.time(18, 5), latitude=-21.172, longitude=-47.812,
                  qtd_gravidade_leve=2, qtd_motocicleta=1, tp_sinistro_primario="CHOQUE"),
        _sinistro(4, dt.date(2031, 4, 10), None, qtd_gravidade_leve=1, tipo_registro="NOTIFICACAO"),
        # coordenada genérica do geocodificador: conta no total, fica fora do mapa
        _sinistro(5, dt.date(2031, 5, 1), dt.time(9, 0), latitude=-21.173, longitude=-47.813,
                  coordenada_generica=True, qtd_gravidade_ileso=1),
    ])
    db.add_all([
        Pessoa(id_pessoa=9_100_001, id_sinistro=9_100_001, ano_sinistro=2031, modo_transporte_vitima="MOTOCICLETA",
               tipo_de_vitima="CONDUTOR", sexo="MASCULINO", idade=22, faixa_etaria="20 a 24", gravidade_lesao="FATAL"),
        Pessoa(id_pessoa=9_100_002, id_sinistro=9_100_002, ano_sinistro=2031, modo_transporte_vitima="AUTOMOVEL",
               tipo_de_vitima="PASSAGEIRO", sexo="FEMININO", idade=40, faixa_etaria="40 a 44", gravidade_lesao="GRAVE"),
        Pessoa(id_pessoa=9_100_003, id_sinistro=9_100_003, ano_sinistro=2031, modo_transporte_vitima="PEDESTRE",
               tipo_de_vitima="PEDESTRE", sexo="MASCULINO", idade=70, faixa_etaria="70 a 74", gravidade_lesao="LEVE"),
    ])
    cidade = lambda cod, nome, pop, obitos, meses=12: IndicadorMunicipio(
        cod_ibge=cod, municipio=nome, ano=2031, meses_com_dados=meses, populacao=pop, fonte_populacao="teste",
        sinistros=obitos * 40, sinistros_fatais=obitos, notificacoes=obitos * 10, obitos=obitos,
        feridos_graves=obitos * 3, feridos_leves=obitos * 20)
    db.add_all([cidade(3543402, "Ribeirão Preto", 700_000, 84), cidade(1, "Cidade Alta", 500_000, 100),
                cidade(2, "Cidade Baixa", 400_000, 20), cidade(3, "Cidade Pequena", 50_000, 30)])
    db.commit()
    db.close()
    yield
    db = SessionLocal()
    db.query(Sinistro).filter(Sinistro.source_name == FONTE).delete()
    db.query(Pessoa).filter(Pessoa.id_pessoa >= 9_100_000).delete()
    db.query(IndicadorMunicipio).filter(IndicadorMunicipio.ano == 2031).delete()
    db.commit()
    db.close()


client = TestClient(app)


def test_resumo_nao_conta_coordenada_generica_como_coordenada():
    r = client.get("/analise/resumo", params={"via": VIA.lower()}).json()
    assert r["sinistros"] == 5 and r["obitos"] == 1 and r["sinistros_fatais"] == 1
    assert r["feridos_graves"] == 1 and r["feridos_leves"] == 3
    assert r["com_coordenada"] == 3 and r["coordenada_generica"] == 1


def test_serie_e_distribuicoes():
    assert client.get("/analise/serie", params={**PERIODO, "granularidade": "ano"}).json() == [
        {"periodo": "2031", "sinistros": 5, "obitos": 1, "feridos_graves": 1, "feridos_leves": 3}]
    meses = [p["periodo"] for p in client.get("/analise/serie", params=PERIODO).json()]
    assert meses == ["2031-03", "2031-04", "2031-05"]

    veiculo = {i["chave"]: i for i in client.get("/analise/distribuicao", params={**PERIODO, "dimensao": "veiculo"}).json()}
    assert veiculo["Motocicleta"]["sinistros"] == 2 and veiculo["Motocicleta"]["obitos"] == 1
    assert veiculo["Automóvel"]["sinistros"] == 2

    hora = client.get("/analise/distribuicao", params={**PERIODO, "dimensao": "hora"}).json()
    assert len(hora) == 24 and hora[7]["sinistros"] == 2
    assert client.get("/analise/distribuicao", params={"dimensao": "inexistente"}).status_code == 422

    matriz = client.get("/analise/dia-hora", params=PERIODO).json()
    assert matriz["matriz"][0][7] == 2 and matriz["sem_hora"] == 1


def test_vias_e_filtro_por_turno():
    assert client.get("/analise/vias", params=PERIODO).json()[0]["via"] == VIA
    assert client.get("/analise/resumo", params={**PERIODO, "turno": "NOITE"}).json()["sinistros"] == 0


def test_bbox_e_geojson_ignoram_coordenada_generica():
    caixa = {**PERIODO, "lat_min": -21.18, "lat_max": -21.16, "lon_min": -47.82, "lon_max": -47.80}
    assert client.get("/analise/resumo", params=caixa).json()["sinistros"] == 3
    geo = client.get("/sinistros/geojson", params={**PERIODO, "logradouro": VIA}).json()["features"]
    assert len(geo) == 3


def test_perfil_das_vitimas():
    v = client.get("/analise/vitimas", params=PERIODO).json()
    assert v["total"] == 3 and v["por_gravidade"]["fatal"] == 1
    modo = {g["chave"]: g for g in v["modo_transporte"]}
    assert modo["MOTOCICLETA"]["fatal"] == 1
    assert [g["chave"] for g in v["faixa_etaria"]] == ["20 a 24", "40 a 44", "70 a 74"]


def test_exportar_csv_respeita_os_filtros():
    r = client.get("/analise/exportar.csv", params={"via": VIA})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    linhas = r.text.strip().splitlines()
    assert linhas[0].startswith("id_sinistro;data_sinistro") and len(linhas) == 6


def test_qualidade_por_ano():
    q = client.get("/analise/qualidade").json()
    ano = next(a for a in q["por_ano"] if a["ano"] == 2031)
    assert ano["sinistros"] == 5 and ano["coordenada_generica"] == 1
    assert ano["pct_coordenada"] == 60.0 and ano["pct_notificacao"] == 20.0
    assert ano["pessoas"] == 3 and ano["pct_idade"] == 100.0


def test_comparacao_entre_cidades():
    c = client.get("/analise/municipios", params={"ano": 2031, "populacao_min": 100_000}).json()
    assert [m["municipio"] for m in c["municipios"]] == ["Cidade Alta", "Ribeirão Preto", "Cidade Baixa"]
    assert c["referencia"]["posicao_obitos"] == 2 and c["referencia"]["obitos_100k"] == 12.0
    assert client.get("/analise/municipios", params={"ano": 1999}).status_code == 404

    serie = client.get("/analise/municipios/serie", params={"cod_ibge": [3543402, 2]}).json()
    assert {s["municipio"] for s in serie} == {"Ribeirão Preto", "Cidade Baixa"}
    assert serie[0]["anos"][0]["obitos_100k"] is not None
