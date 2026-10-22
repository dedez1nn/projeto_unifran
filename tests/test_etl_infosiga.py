"""Carga do zip do InfoSiga (`src/etl/infosiga.py`) com um zip sintético no
formato oficial: Ribeirão Preto e outra cidade, um arquivo mensal antigo
com o mesmo sinistro e um ponto genérico do geocodificador."""

import zipfile

import pytest

pd = pytest.importorskip("pandas")

from app.db.models import IndicadorMunicipio, Pessoa, Sinistro  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.services.ingestion_service import ingest_csv_bytes  # noqa: E402
from etl import infosiga  # noqa: E402

CAB_SINISTROS = ("id_sinistro;tipo_registro;data_sinistro;ano_sinistro;mes_sinistro;dia_sinistro;hora_sinistro;"
                 "ano_mes_sinistro;dia_da_semana;turno;logradouro;numero_logradouro;tipo_via;tipo_local;latitude;"
                 "longitude;cod_ibge;municipio;regiao_administrativa;qtd_gravidade_fatal;qtd_gravidade_grave;"
                 "qtd_gravidade_leve;qtd_motocicleta")
CAB_PESSOAS = ("id_sinistro;id_pessoa;id_veiculo;cod_ibge;municipio;tipo_via;tipo_veiculo_vitima;tipo_de_vitima;"
               "modo_transporte_vitima;sexo;idade;gravidade_lesao;faixa_etaria_demografica;data_sinistro;"
               "ano_sinistro;local_obito;tempo_sinistro_obito")
ID0 = 8_800_000


def _sinistro(i, municipio, cod, lat="", lon="", rua=None, fatal="", tipo="SINISTRO NAO FATAL", ano=2030):
    rua = rua or f"RUA {i}"
    return (f"{ID0 + i};{tipo};10/0{1 + i % 9}/{ano};{ano};0{1 + i % 9};10;08:30;{ano}/01;Segunda-feira;MANHA;{rua};"
            f"10;VIAS URBANAS;PUBLICO;{lat};{lon};{cod};{municipio};RIBEIRAO PRETO;{fatal};;1;1")


@pytest.fixture(scope="module")
def zip_infosiga(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("infosiga")
    rp = [_sinistro(0, "RIBEIRAO PRETO", 3543402, "-21,17", "-47,81", "AVENIDA X", fatal="1", tipo="SINISTRO FATAL"),
          _sinistro(1, "RIBEIRAO PRETO", 3543402, "-21,18", "-47,80", "AVENIDA X")]
    # 20 sinistros de 20 ruas diferentes na mesma coordenada: ponto genérico
    rp += [_sinistro(10 + k, "RIBEIRAO PRETO", 3543402, "-21,2079", "-47,8521", f"RUA GENERICA {k}") for k in range(20)]
    outra = [_sinistro(50 + k, "FRANCA", 3516200, fatal="1" if k < 3 else "", tipo="SINISTRO FATAL" if k < 3 else "SINISTRO NAO FATAL")
             for k in range(5)]
    sinistros = "\n".join([CAB_SINISTROS, *rp, *outra]) + "\n"
    pessoas = "\n".join([CAB_PESSOAS,
                         f"{ID0};1;;3543402;RIBEIRAO PRETO;VIAS URBANAS;MOTOCICLETA;CONDUTOR;MOTOCICLETA;MASCULINO;23;FATAL;20 a 24;10/01/2030;2030;VIA;0",
                         f"{ID0 + 1};2;;3543402;RIBEIRAO PRETO;VIAS URBANAS;;PEDESTRE;PEDESTRE;FEMININO;;LEVE;NAO DISPONIVEL;10/02/2030;2030;;",
                         f"{ID0 + 50};3;;3516200;FRANCA;VIAS URBANAS;;CONDUTOR;AUTOMOVEL;MASCULINO;40;ILESO;40 a 44;10/01/2030;2030;;"]) + "\n"
    caminho = pasta / "dados_infosiga.zip"
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("sinistros_2030-2030.csv", sinistros.encode("latin-1"))
        z.writestr("pessoas_2030-2030.csv", pessoas.encode("latin-1"))
    populacao = pasta / "populacao.csv"
    populacao.write_text("cod_ibge;municipio;ano;populacao;fonte\n3543402;Ribeirão Preto;2030;700000;teste\n"
                         "3516200;Franca;2030;350000;teste\n", encoding="utf-8")
    return caminho, populacao


@pytest.fixture(scope="module")
def db():
    Base.metadata.create_all(bind=engine)
    sessao = SessionLocal()
    yield sessao
    sessao.query(Sinistro).filter(Sinistro.id_sinistro >= ID0, Sinistro.id_sinistro < ID0 + 1000).delete()
    sessao.query(Pessoa).filter(Pessoa.id_sinistro >= ID0, Pessoa.id_sinistro < ID0 + 1000).delete()
    sessao.query(IndicadorMunicipio).delete()
    sessao.query(Sinistro).update({Sinistro.coordenada_generica: False})
    sessao.commit()
    sessao.close()


def test_carga_filtra_o_municipio_e_remove_o_mensal_duplicado(db, zip_infosiga):
    caminho, _ = zip_infosiga
    # arquivo mensal antigo, já ingerido, com o mesmo sinistro 0
    mensal = (CAB_SINISTROS + "\n" + _sinistro(0, "RIBEIRAO PRETO", 3543402, "-21,17", "-47,81", "AVENIDA X") + "\n").encode("latin-1")
    ingest_csv_bytes(db, mensal, "sinistros_01-2030.csv")

    resumos, duplicados = infosiga.carregar_sinistros(db, caminho)
    assert resumos[0].inserted == 22 and duplicados == 1
    ids = db.query(Sinistro).filter(Sinistro.id_sinistro >= ID0, Sinistro.id_sinistro < ID0 + 1000)
    assert ids.count() == 22
    assert {s.source_name for s in ids} == {"sinistros_2030_2030"}

    # reingerir é idempotente
    resumos, duplicados = infosiga.carregar_sinistros(db, caminho)
    assert resumos[0].inserted == 0 and resumos[0].updated == 22 and duplicados == 0


def test_marca_so_o_ponto_generico(db):
    assert infosiga.marcar_coordenadas_genericas(db) == 20
    gen = db.query(Sinistro).filter(Sinistro.coordenada_generica.is_(True)).all()
    assert {s.logradouro for s in gen} == {f"RUA GENERICA {k}" for k in range(20)}


def test_pessoas_do_municipio(db, zip_infosiga):
    caminho, _ = zip_infosiga
    assert infosiga.carregar_pessoas(db, caminho) == 2
    morto = db.query(Pessoa).filter(Pessoa.id_pessoa == 1).one()
    assert morto.gravidade_lesao == "FATAL" and morto.idade == 23 and morto.modo_transporte_vitima == "MOTOCICLETA"
    assert db.query(Pessoa).filter(Pessoa.id_pessoa == 2).one().idade is None


def test_indicadores_de_todas_as_cidades(db, zip_infosiga):
    caminho, populacao = zip_infosiga
    assert infosiga.carregar_indicadores(db, caminho, populacao) == 2
    franca = db.query(IndicadorMunicipio).filter(IndicadorMunicipio.cod_ibge == 3516200).one()
    assert (franca.sinistros, franca.sinistros_fatais, franca.obitos, franca.populacao) == (5, 3, 3, 350000)
    rp = db.query(IndicadorMunicipio).filter(IndicadorMunicipio.cod_ibge == 3543402).one()
    assert rp.municipio == "Ribeirão Preto" and rp.sinistros == 22 and rp.meses_com_dados == 9
