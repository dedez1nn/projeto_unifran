"""Pipeline de treino (`src/ml/`) e leitura do resultado pela API.

Usa uma base sintética pequena no formato bruto da Senatran: 6 vias, cada
uma numa célula, de 2019 a 2026-04, com um mês sem dados (2025-11), uma via
que esquenta nos últimos 6 meses e um aglomerado de acidentes com óbito.
"""

import pytest

# Dependências de requirements-ml.txt: sem elas, o módulo é pulado em vez de quebrar.
np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")
pytest.importorskip("sklearn")

from fastapi.testclient import TestClient  # noqa: E402

from app.db.models import MlExecucao, RiscoCelula  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from ml import ocorrencia, pontos_criticos, serie_mensal, tendencia, veiculos  # noqa: E402
from ml.dados import carregar_acidentes, carregar_veiculos  # noqa: E402
from ml.publicar import publicar  # noqa: E402
from ml.treino import treinar  # noqa: E402

VIAS = {
    "AVENIDA UM": (-21.170, -47.810, 9),
    "AVENIDA DOIS": (-21.180, -47.800, 6),
    "RUA TRES": (-21.160, -47.820, 4),
    "RUA QUATRO": (-21.190, -47.790, 3),
    "RUA CINCO": (-21.200, -47.830, 2),
    "RUA QUENTE": (-21.150, -47.780, 2),
}
COLUNAS = ["num_acidente", "data_acidente", "hora_acidente", "latitude_acidente", "longitude_acidente",
           "end_acidente", "qtde_obitos", "qtde_envolvidos", "tp_acidente"]


def _base_sintetica() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    linhas, n = [], 0
    for mes in pd.period_range("2019-01", "2026-04", freq="M"):
        if str(mes) == "2025-11":
            continue  # mês sem dados na fonte
        geo = mes >= pd.Period("2023-01", "M")
        for via, (lat, lon, taxa) in VIAS.items():
            if via == "RUA QUENTE" and mes > pd.Period("2025-10", "M"):
                taxa = 14
            for _ in range(rng.poisson(taxa)):
                n += 1
                dia = int(rng.integers(1, 28))
                sem_coord = (not geo) or rng.random() < 0.05
                linhas.append([n, f"{mes}-{dia:02d}", f"{int(rng.integers(0, 24)):02d}3000",
                               "" if sem_coord else f"{lat + rng.normal(0, 0.0008):.7f}",
                               "" if sem_coord else f"{lon + rng.normal(0, 0.0008):.7f}",
                               via, 0, 2, "COLISAO"])
    # rua que só ganha acidente geocodificado em 2024-07, com um acidente sem
    # coordenada bem antes (2023-03): é o caso do teste de vazamento
    for i in range(10):
        n += 1
        linhas.append([n, f"2024-{7 + i % 6:02d}-0{1 + i % 9}", "100000", f"{-21.2100 + i * 0.0001:.7f}",
                       "-47.7700000", "RUA NOVA", 0, 1, "CHOQUE"])
    n += 1
    linhas.append([n, "2023-03-15", "100000", "", "", "RUA NOVA", 0, 1, "CHOQUE"])
    # aglomerado de 4 acidentes com óbito num raio de ~30 m
    for i in range(4):
        n += 1
        linhas.append([n, f"2024-0{i + 1}-10", "220000", f"{-21.1755 + i * 0.0001:.7f}", "-47.8155000",
                       "AVENIDA UM", 1, 1, "ATROPELAMENTO"])
    return pd.DataFrame(linhas, columns=COLUNAS)


@pytest.fixture(scope="module")
def csv_sintetico(tmp_path_factory):
    caminho = tmp_path_factory.mktemp("ml") / "acidentes.csv"
    _base_sintetica().to_csv(caminho, sep=";", index=False, encoding="latin-1")
    return caminho


@pytest.fixture(scope="module")
def csv_veiculos(csv_sintetico, tmp_path_factory):
    """Na AVENIDA UM, 80% dos acidentes envolvem moto; nas outras, 20%.
    Um terço dos acidentes fica com tipo DESCONHECIDO."""
    rng = np.random.default_rng(1)
    linhas = []
    for a in pd.read_csv(csv_sintetico, sep=";", encoding="latin-1").itertuples():
        if rng.random() < 1 / 3:
            linhas.append([a.num_acidente, "DESCONHECIDO", "NAO INFORMADO", 1])
            continue
        p_moto = 0.8 if a.end_acidente == "AVENIDA UM" else 0.2
        linhas.append([a.num_acidente, "MOTOCICLETA" if rng.random() < p_moto else "AUTOMOVEL", "NAO INFORMADO", 1])
    caminho = tmp_path_factory.mktemp("ml") / "veiculos.csv"
    pd.DataFrame(linhas, columns=["num_acidente", "tipo_veiculo", "ind_veic_estrangeiro", "qtde_veiculos"]) \
        .to_csv(caminho, sep=";", index=False, encoding="latin-1")
    return caminho


@pytest.fixture(scope="module")
def base(csv_sintetico):
    return ocorrencia.preparar_geo(carregar_acidentes(csv_sintetico))


def test_carga_do_formato_bruto_converte_hora_hhmmss(tmp_path):
    csv = tmp_path / "bruto.csv"
    pd.DataFrame([
        [1, "2019-03-01", "013900", "-21.17", "-47.81", "RUA A", 0, 1, "CHOQUE"],
        [2, "2019-03-02", "999999", "", "", "AV. B", 0, 1, "CHOQUE"],
        [3, "2019-03-03", "180400", "", "", "", 1, 1, "CHOQUE"],
        [4, "2018-12-31", "120000", "", "", "RUA A", 1, 1, "CHOQUE"],
    ], columns=COLUNAS).to_csv(csv, sep=";", index=False, encoding="latin-1")
    df = carregar_acidentes(csv)
    assert len(df) == 3  # 2018 fica de fora (só tem óbitos)
    assert df["hora"].iloc[0] == 1 and np.isnan(df["hora"].iloc[1]) and df["hora"].iloc[2] == 18
    assert df["rua"].tolist() == ["RUA A", "AVENIDA B", ""]


def test_carga_do_formato_tratado(tmp_path):
    csv = tmp_path / "tratados.csv"
    pd.DataFrame({"num_acidente": [1], "data_acidente": ["2024-05-05"], "hora": [7], "latitude": [-21.17],
                  "longitude": [-47.81], "endereco": ["RUA A"], "qtde_obitos": [0], "qtde_envolvidos": [2],
                  "tp_acidente": ["CHOQUE"]}).to_csv(csv, sep=";", index=False)
    df = carregar_acidentes(csv)
    assert df["hora"].iloc[0] == 7 and df["fim_de_semana"].iloc[0] == 1


def test_alocacao_por_rua_nao_usa_o_futuro(base):
    """Sem coordenada, o acidente é distribuído pelas células da rua com
    pesos calculados só até o corte: antes de existir qualquer acidente
    geocodificado da rua, ele não pode ser alocado."""
    primeiro_geo = int(base.validos.loc[base.validos["rua"] == "RUA NOVA", "m"].min())
    linhas_rua = lambda g: g[(g["imputada"] == 1) & (g["rua"] == "RUA NOVA")]
    assert primeiro_geo == 18  # 2024-07
    assert linhas_rua(ocorrencia.alocar(base, primeiro_geo - 1)).empty
    assert not linhas_rua(ocorrencia.alocar(base, base.ultimo_mes)).empty


def test_mes_sem_dados_na_fonte_nao_conta_como_zero(base):
    assert base.resumo["meses_ausentes"] == ["2025-11"]


def test_escolher_modelo_e_prever_aceitam_a_media_historica():
    media = pd.DataFrame({"dev_poisson": [1.0, 0.5, 1.2, 1.5, 1.1]}, index=list(ocorrencia.MODELOS))
    assert ocorrencia.escolher_modelo(media) == "BASE_taxa"  # BASE_12m fica de fora mesmo sendo a menor
    X = pd.DataFrame({"r_total": [1.0], "r_12": [2.0], "eb_rate": [3.0]})
    assert ocorrencia.prever("BASE_taxa", X, np.zeros(1), 12)[0] == 12.0
    assert ocorrencia.prever("MISTO_GBM_EB", X, np.array([6.0]), 12)[0] == 21.0


def test_tendencia_acende_so_a_rua_que_esquentou(base):
    g = ocorrencia.alocar(base, base.ultimo_mes)
    alta = tendencia.zonas_em_alta(g, base.ultimo_mes)
    celulas_quentes = set(alta.index[alta["em_alta"]])
    rua_quente = set(g.loc[g["rua"] == "RUA QUENTE", "celula"].mode())
    assert celulas_quentes and celulas_quentes <= rua_quente


def test_fracao_por_veiculo_separa_a_via_das_motos(base, csv_veiculos):
    g = ocorrencia.alocar(base, base.ultimo_mes)
    celulas, _, _ = ocorrencia.gerar_ranking(base, "BASE_taxa")
    por_veiculo, resumo = veiculos.por_celula(g, carregar_veiculos(csv_veiculos), celulas)
    moto = por_veiculo[por_veiculo["veiculo"] == "moto"].set_index("celula")
    # célula principal de cada via (as menores são puxadas para a média da
    # cidade pela suavização, que é o comportamento esperado)
    principal = celulas.sort_values("n_total").groupby("rua_principal").tail(1) \
        .reset_index().set_index("rua_principal")["celula"]
    assert moto.loc[principal["AVENIDA UM"], "fracao"] > 0.6
    assert moto.loc[principal["AVENIDA DOIS"], "fracao"] < 0.35
    assert 0.6 < resumo["cobertura_tipo_veiculo"] < 0.73   # 2/3 com tipo informado
    assert (moto["acidentes_esperados"] <= celulas["acidentes_esperados"].reindex(moto.index) + 1e-9).all()


def test_pontos_criticos_agrupa_obitos_proximos(base):
    pontos = pontos_criticos.pontos_criticos(base.validos)
    assert len(pontos) == 1
    assert pontos.iloc[0]["n_obitos"] == 4 and pontos.iloc[0]["rua_principal"] == "AVENIDA UM"


def test_serie_mensal_preve_12_meses_e_pula_mes_ausente(csv_sintetico):
    serie = serie_mensal.serie_observada(carregar_acidentes(csv_sintetico))
    assert np.isnan(serie.loc[pd.Period("2025-11", "M"), "real"])
    prev = serie_mensal.prever(serie)
    futuro = prev[prev["futuro"]]
    assert len(futuro) == 12 and futuro["mes"].iloc[0] == "2026-05"
    assert (futuro["limite_inferior"] <= futuro["previsto"]).all()
    assert (futuro["previsto"] <= futuro["limite_superior"]).all()


def test_rotas_de_risco_sem_modelo_publicado():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.query(MlExecucao).delete()
    db.query(RiscoCelula).delete()
    db.commit()
    db.close()
    client = TestClient(app)
    assert client.get("/risco/modelo").status_code == 404
    assert client.get("/risco/simular", params={"via": "RUA A", "dia_semana": 0, "horas": [8]}).status_code == 404
    assert client.get("/risco/zonas").json() == {"type": "FeatureCollection", "features": []}


def test_treino_publica_e_api_le(csv_sintetico, csv_veiculos):
    resultado = treinar(csv_sintetico, csv_veiculos, log=lambda *_: None)
    publicar(resultado)
    client = TestClient(app)

    modelo = client.get("/risco/modelo").json()
    assert modelo["modelo_ocorrencia"] in ocorrencia.MODELOS
    assert modelo["janela_previsao"] == "2026-05 a 2027-04"

    zonas = client.get("/risco/zonas").json()["features"]
    assert zonas and zonas[0]["geometry"]["type"] == "Polygon"
    assert zonas[0]["properties"]["rua_principal"] == "AVENIDA UM"
    assert {z["properties"]["nivel_risco"] for z in zonas} <= {"ALTO", "MEDIO", "BAIXO"}
    so_alto = client.get("/risco/zonas", params={"nivel": "ALTO"}).json()["features"]
    assert all(z["properties"]["nivel_risco"] == "ALTO" for z in so_alto)

    resumo_veiculos = client.get("/risco/veiculos").json()
    assert {v["veiculo"] for v in resumo_veiculos["veiculos"]} == {"moto", "carro", "caminhao", "onibus"}
    zonas_moto = client.get("/risco/zonas", params={"veiculo": "moto"}).json()["features"]
    assert len(zonas_moto) == len(zonas)
    assert all(z["properties"]["veiculo"] == "moto" for z in zonas_moto)
    assert zonas_moto[0]["properties"]["rua_principal"] == "AVENIDA UM"
    assert client.get("/risco/zonas", params={"veiculo": "bicicleta"}).status_code == 422

    vias = [v["via"] for v in client.get("/risco/vias").json()]
    assert vias[0] == "AVENIDA UM" and set(vias) <= set(VIAS) | {"RUA NOVA"}

    sim = client.get("/risco/simular", params={"via": "AVENIDA UM", "dia_semana": 4, "horas": [17, 18]})
    assert sim.status_code == 200
    assert 0 <= sim.json()["indice"] <= 100 and sim.json()["acidentes_esperados_janela"] > 0
    assert client.get("/risco/simular", params={"via": "NAO EXISTE", "dia_semana": 4, "horas": [17]}).status_code == 404
    assert client.get("/risco/simular", params={"via": "AVENIDA UM", "dia_semana": 4, "horas": [24]}).status_code == 422

    agora = client.get("/risco/agora", params={"dia_semana": 0, "hora": 8, "limit": 3}).json()
    assert len(agora) == 3

    assert client.get("/risco/pontos-criticos").json()[0]["n_obitos"] == 4
    mensal = client.get("/risco/previsao-mensal").json()
    assert sum(m["futuro"] for m in mensal) == 12

    matriz = client.get("/risco/perfil-horario").json()["matriz"]
    assert len(matriz) == 7 and abs(sum(map(sum, matriz)) - 1) < 1e-6
    assert client.get("/risco/perfil-horario", params={"via": "NAO EXISTE"}).status_code == 404


def test_treino_sem_tabela_de_veiculos_nao_oferece_o_filtro(csv_sintetico):
    publicar(treinar(csv_sintetico, log=lambda *_: None))
    client = TestClient(app)
    assert client.get("/risco/veiculos").status_code == 404
    assert client.get("/risco/zonas", params={"veiculo": "moto"}).json()["features"] == []
