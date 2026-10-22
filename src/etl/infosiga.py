"""Carga do histórico do InfoSiga (zip com `sinistros_*`, `pessoas_*` e
`veiculos_*` do estado inteiro, 2015-2026).

Três produtos:

- **sinistros** de Ribeirão Preto: pré-filtrados aqui e passados para a
  ingestão de sempre (`services/ingestion_service.py`), então valem o mesmo
  mapeamento por alias e o mesmo upsert idempotente;
- **pessoas** envolvidas nesses sinistros (tabela `pessoas`): idade, sexo,
  tipo de vítima, gravidade;
- **indicadores anuais de todos os municípios** (tabela
  `indicadores_municipios`), com a população do IBGE, para comparar cidades.
  Só os totais por município/ano são guardados, não as 1,4 milhão de linhas.

Os arquivos têm ~150 MB cada, por isso a leitura é em blocos.
"""

from __future__ import annotations

import re
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import IndicadorMunicipio, Pessoa, Sinistro
from app.schemas.sinistro import IngestionSummary
from app.services.ingestion_service import _source_name_from_filename, ingest_csv_bytes

BLOCO = 100_000
_FONTE_INFOSIGA = re.compile(r"^sinistros_")


def _membros(zip_path: str | Path, prefixo: str) -> list[str]:
    with zipfile.ZipFile(zip_path) as z:
        return sorted(n for n in z.namelist() if Path(n).name.startswith(prefixo) and n.endswith(".csv"))


def _blocos(zip_path: str | Path, membro: str, usecols=None) -> Iterator[pd.DataFrame]:
    with zipfile.ZipFile(zip_path) as z, z.open(membro) as f:
        yield from pd.read_csv(f, sep=";", encoding="latin-1", dtype=str, keep_default_na=False,
                               usecols=usecols, chunksize=BLOCO)


def _do_municipio(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["municipio"].str.strip().str.upper() == settings.municipio_alvo]


def _numero(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie.str.replace(",", ".", regex=False), errors="coerce")


# ----------------------------------------------------------------------------
# Sinistros de Ribeirão Preto
# ----------------------------------------------------------------------------
def carregar_sinistros(db: Session, zip_path: str | Path) -> tuple[list[IngestionSummary], int]:
    """Ingere os sinistros do município de cada arquivo do zip. Depois remove
    as linhas de outros arquivos do InfoSiga (ex.: o mensal
    `sinistros_12-2025.csv`) cujo `id_sinistro` já veio na série completa:
    o upsert é por arquivo, então sem isso o mesmo sinistro contaria duas
    vezes. Retorna os resumos e quantas linhas duplicadas saíram."""
    resumos, fontes, ids = [], [], set()
    for membro in _membros(zip_path, "sinistros_"):
        rp = pd.concat([_do_municipio(b) for b in _blocos(zip_path, membro)])
        ids.update(pd.to_numeric(rp["id_sinistro"], errors="coerce").dropna().astype(int))
        nome = Path(membro).name
        resumos.append(ingest_csv_bytes(db, rp.to_csv(sep=";", index=False).encode("latin-1", "replace"), nome))
        fontes.append(_source_name_from_filename(nome))

    duplicados = (db.query(Sinistro)
                  .filter(Sinistro.source_name.notin_(fontes), Sinistro.id_sinistro.in_(ids))
                  .all())
    duplicados = [s for s in duplicados if _FONTE_INFOSIGA.match(s.source_name)]
    for s in duplicados:
        db.delete(s)
    db.commit()
    return resumos, len(duplicados)


PLACEHOLDER_MIN_N, PLACEHOLDER_MIN_ENDERECOS = 20, 10   # mesma regra de `ml.ocorrencia`


def marcar_coordenadas_genericas(db: Session) -> int:
    """Marca como genérica a coordenada usada por 20+ sinistros de 10+
    endereços diferentes (posição padrão do geocodificador, não o local do
    sinistro). Marcos de quilômetro de rodovia, que repetem a coordenada
    para o mesmo logradouro, não entram. Retorna quantos sinistros ficaram
    marcados."""
    linhas = db.query(Sinistro.id, Sinistro.latitude, Sinistro.longitude, Sinistro.logradouro) \
        .filter(Sinistro.latitude.is_not(None), Sinistro.longitude.is_not(None)).all()
    if not linhas:
        return 0
    df = pd.DataFrame(linhas, columns=["id", "lat", "lon", "rua"])
    chave = df["lat"].round(5).astype(str) + "_" + df["lon"].round(5).astype(str)
    grupos = df.groupby(chave).agg(n=("id", "size"), enderecos=("rua", "nunique"))
    genericas = set(grupos[(grupos["n"] >= PLACEHOLDER_MIN_N) & (grupos["enderecos"] >= PLACEHOLDER_MIN_ENDERECOS)].index)
    ids = [int(i) for i in df.loc[chave.isin(genericas), "id"]]
    db.query(Sinistro).update({Sinistro.coordenada_generica: False}, synchronize_session=False)
    for inicio in range(0, len(ids), 500):
        db.query(Sinistro).filter(Sinistro.id.in_(ids[inicio:inicio + 500])) \
            .update({Sinistro.coordenada_generica: True}, synchronize_session=False)
    db.commit()
    return len(ids)


# ----------------------------------------------------------------------------
# Pessoas envolvidas
# ----------------------------------------------------------------------------
_COLS_PESSOAS = ["id_sinistro", "id_pessoa", "municipio", "tipo_veiculo_vitima", "tipo_de_vitima",
                 "modo_transporte_vitima", "sexo", "idade", "gravidade_lesao", "faixa_etaria_demografica",
                 "data_sinistro", "ano_sinistro", "local_obito", "tempo_sinistro_obito"]


def pessoas_do_municipio(zip_path: str | Path) -> pd.DataFrame:
    partes = [_do_municipio(b) for m in _membros(zip_path, "pessoas_") for b in _blocos(zip_path, m, _COLS_PESSOAS)]
    p = pd.concat(partes).drop_duplicates("id_pessoa", keep="last")
    texto = lambda c: p[c].str.strip().str.upper().replace("", None)
    return pd.DataFrame({
        "id_pessoa": pd.to_numeric(p["id_pessoa"], errors="coerce").astype("Int64"),
        "id_sinistro": pd.to_numeric(p["id_sinistro"], errors="coerce").astype("Int64"),
        "data_sinistro": pd.to_datetime(p["data_sinistro"], format="%d/%m/%Y", errors="coerce").dt.date,
        "ano_sinistro": pd.to_numeric(p["ano_sinistro"], errors="coerce").astype("Int64"),
        "tipo_de_vitima": texto("tipo_de_vitima"),
        "modo_transporte_vitima": texto("modo_transporte_vitima"),
        "tipo_veiculo_vitima": texto("tipo_veiculo_vitima"),
        "sexo": texto("sexo"),
        "idade": _numero(p["idade"]).where(lambda x: x.between(0, 110)).astype("Int64"),
        "faixa_etaria": p["faixa_etaria_demografica"].str.strip().replace("", None),
        "gravidade_lesao": texto("gravidade_lesao"),
        "local_obito": texto("local_obito"),
        "tempo_sinistro_obito": _numero(p["tempo_sinistro_obito"]).astype("Int64"),
    }).dropna(subset=["id_pessoa", "id_sinistro"])


def carregar_pessoas(db: Session, zip_path: str | Path) -> int:
    """Substitui a tabela `pessoas` inteira (é derivada do zip, não tem
    edição manual a preservar)."""
    df = pessoas_do_municipio(zip_path)
    registros = df.astype(object).where(df.notna(), None).to_dict(orient="records")
    db.query(Pessoa).delete()
    db.bulk_insert_mappings(Pessoa, registros)
    db.commit()
    return len(registros)


# ----------------------------------------------------------------------------
# Indicadores por município (estado inteiro)
# ----------------------------------------------------------------------------
_COLS_AGREGADO = ["cod_ibge", "municipio", "ano_sinistro", "mes_sinistro", "tipo_registro",
                  "qtd_gravidade_fatal", "qtd_gravidade_grave", "qtd_gravidade_leve"]


def indicadores_municipios(zip_path: str | Path, populacao_csv: str | Path) -> pd.DataFrame:
    partes = []
    for membro in _membros(zip_path, "sinistros_"):
        for b in _blocos(zip_path, membro, _COLS_AGREGADO):
            b = b.assign(
                cod_ibge=pd.to_numeric(b["cod_ibge"], errors="coerce"),
                ano=pd.to_numeric(b["ano_sinistro"], errors="coerce"),
                mes=pd.to_numeric(b["mes_sinistro"], errors="coerce"),
                fatal=(b["tipo_registro"] == "SINISTRO FATAL").astype(int),
                notificacao=(b["tipo_registro"] == "NOTIFICACAO").astype(int),
                obitos=_numero(b["qtd_gravidade_fatal"]).fillna(0),
                graves=_numero(b["qtd_gravidade_grave"]).fillna(0),
                leves=_numero(b["qtd_gravidade_leve"]).fillna(0),
            ).dropna(subset=["cod_ibge", "ano"])
            partes.append(b.groupby(["cod_ibge", "ano"]).agg(
                sinistros=("tipo_registro", "size"), sinistros_fatais=("fatal", "sum"),
                notificacoes=("notificacao", "sum"), obitos=("obitos", "sum"),
                feridos_graves=("graves", "sum"), feridos_leves=("leves", "sum"),
                municipio_infosiga=("municipio", "first"), meses=("mes", lambda s: set(s.dropna().astype(int)))))
    bruto = pd.concat(partes).reset_index()
    soma = bruto.groupby(["cod_ibge", "ano"]).agg(
        sinistros=("sinistros", "sum"), sinistros_fatais=("sinistros_fatais", "sum"),
        notificacoes=("notificacoes", "sum"), obitos=("obitos", "sum"),
        feridos_graves=("feridos_graves", "sum"), feridos_leves=("feridos_leves", "sum"),
        municipio_infosiga=("municipio_infosiga", "first")).reset_index()
    # meses com dados no estado (não por município): um município pequeno sem
    # sinistro num mês não torna o ano "parcial"
    meses = bruto.groupby("ano")["meses"].agg(lambda s: len(set().union(*s))).rename("meses_com_dados")
    soma = soma.join(meses, on="ano")

    pop = pd.read_csv(populacao_csv, sep=";", dtype={"cod_ibge": int})
    soma = soma.merge(pop.rename(columns={"fonte": "fonte_populacao"}), on=["cod_ibge", "ano"], how="left")
    soma["municipio"] = soma["municipio"].fillna(soma["municipio_infosiga"].str.title())
    colunas = ["cod_ibge", "municipio", "ano", "meses_com_dados", "populacao", "fonte_populacao", "sinistros",
               "sinistros_fatais", "notificacoes", "obitos", "feridos_graves", "feridos_leves"]
    soma = soma[colunas].astype({"cod_ibge": int, "ano": int})
    for c in colunas[6:]:
        soma[c] = soma[c].round().astype(int)
    return soma


def carregar_indicadores(db: Session, zip_path: str | Path, populacao_csv: str | Path) -> int:
    df = indicadores_municipios(zip_path, populacao_csv)
    registros = df.astype(object).where(df.notna(), None).to_dict(orient="records")
    db.query(IndicadorMunicipio).delete()
    db.bulk_insert_mappings(IndicadorMunicipio, registros)
    db.commit()
    return len(registros)
