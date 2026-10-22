"""Carga da base RENAEST (acidentes de Ribeirão Preto) para o treino.

Aceita dois formatos com o mesmo conteúdo:

- o CSV bruto da Senatran (`data/acidentes_ribeirao_preto.csv`: `latin-1`,
  `hora_acidente` como `HHMMSS`, `end_acidente`, `latitude_acidente`...);
- a tabela `acidentes_tratados` do banco do time de dados, exportada para CSV
  (`hora` já em 0-23, `endereco`, `latitude`...).

Os dois viram o mesmo DataFrame normalizado, então o resto do pipeline não
precisa saber de onde os dados vieram.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd

# 2018 só traz os acidentes com óbito (é o início da série), então entrar com
# ele enviesaria qualquer taxa ou proporção. A série útil começa em 2019.
INICIO_SERIE = "2019-01-01"

# Na base bruta, `999999` em `hora_acidente` é o código de hora ausente.
_HORA_AUSENTE = 999999


def _ler_csv(caminho: str | Path) -> pd.DataFrame:
    conteudo = Path(caminho).read_bytes()
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            texto = conteudo.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    return pd.read_csv(io.StringIO(texto), sep=";", dtype=str, keep_default_na=False)


def _numero(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie.replace({"": None, "\\N": None}), errors="coerce")


def _hora_bruta(serie: pd.Series) -> pd.Series:
    """`HHMMSS` -> hora (0-23). Ler como número direto daria 13900 para
    "013900", que é o bug que fazia quase tudo cair em "Noite" no notebook."""
    h = _numero(serie)
    h = h.where(h != _HORA_AUSENTE) // 10000
    return h.where(h.between(0, 23))


def carregar_acidentes(caminho: str | Path) -> pd.DataFrame:
    bruto = _ler_csv(caminho)
    formato_bruto = "hora_acidente" in bruto.columns

    df = pd.DataFrame({"num_acidente": bruto["num_acidente"].astype(str)})
    df["data_acidente"] = pd.to_datetime(bruto["data_acidente"], errors="coerce")
    if formato_bruto:
        df["hora"] = _hora_bruta(bruto["hora_acidente"])
        df["latitude"] = _numero(bruto["latitude_acidente"])
        df["longitude"] = _numero(bruto["longitude_acidente"])
        df["endereco"] = bruto["end_acidente"]
    else:
        df["hora"] = _numero(bruto["hora"]).where(lambda h: h.between(0, 23))
        df["latitude"] = _numero(bruto["latitude"])
        df["longitude"] = _numero(bruto["longitude"])
        df["endereco"] = bruto["endereco"]

    df["qtde_obitos"] = _numero(bruto["qtde_obitos"]).fillna(0).astype(int)
    df["qtde_envolvidos"] = _numero(bruto["qtde_envolvidos"])
    df["tp_acidente"] = bruto["tp_acidente"].str.strip().str.upper()

    df = df.dropna(subset=["data_acidente"])
    df = df[df["data_acidente"] >= INICIO_SERIE].copy()
    df["obito"] = (df["qtde_obitos"] > 0).astype(int)
    # Derivados da data (e não da coluna `dia_semana` da fonte) para valer
    # igual nos dois formatos: segunda = 0 ... domingo = 6.
    df["dia_semana"] = df["data_acidente"].dt.dayofweek
    df["fim_de_semana"] = (df["dia_semana"] >= 5).astype(int)
    df["rua"] = normalizar_rua(df["endereco"])
    return df.reset_index(drop=True)


def normalizar_rua(serie: pd.Series) -> pd.Series:
    s = serie.fillna("").astype(str).str.replace("\\", "", regex=False).str.strip().str.upper()
    s = s.str.replace(r"\s+", " ", regex=True)
    # Mesma via grafada de dois jeitos ("AV. EDUARDO..." e "AVENIDA EDUARDO...").
    s = s.str.replace(r"^AV\.? ", "AVENIDA ", regex=True).str.replace(r"^R\.? ", "RUA ", regex=True)
    return s.where(~s.isin(["", "LOGRADOURO NAO INFORMADO", "NAN", "NAO INFORMADO"]), "")


def diagnostico_qualidade(df: pd.DataFrame, bbox: dict) -> pd.DataFrame:
    """Preenchimento por ano: é o que justifica cada recorte do pipeline
    (coordenadas só de 2023 em diante, óbito como único desfecho de gravidade)."""
    ano = df["data_acidente"].dt.year
    coord = df["latitude"].between(*bbox["lat"]) & df["longitude"].between(*bbox["lon"])
    return pd.DataFrame({
        "n": ano.value_counts().sort_index(),
        "pct_com_ferido": ((df["qtde_envolvidos"] > 0).groupby(ano).mean() * 100).round(1),
        "pct_obito": (df["obito"].groupby(ano).mean() * 100).round(1),
        "pct_tp_acid_informado": ((~df["tp_acidente"].isin(["DESCONHECIDO", "NAO INFORMADO", ""]))
                                  .groupby(ano).mean() * 100).round(0),
        "pct_coord_valida": (coord.groupby(ano).mean() * 100).round(0),
        "pct_hora_valida": (df["hora"].notna().groupby(ano).mean() * 100).round(0),
    }).replace({np.nan: None})


# Tipos de veículo da RENAEST agrupados nas categorias do filtro do mapa.
# Bicicleta fica de fora: são só 57 registros na base inteira.
CATEGORIAS_VEICULO = {
    "moto": ("MOTOCICLETA", "MOTONETA", "CICLOMOTOR", "TRICICLO"),
    "carro": ("AUTOMOVEL", "CAMINHONETE", "CAMIONETA", "UTILITARIO"),
    "caminhao": ("CAMINHAO", "CAMINHAO-TRATOR", "SEMIRREBOQUE", "REBOQUE"),
    "onibus": ("ONIBUS", "MICRO-ONIBUS"),
}
_TIPO_PARA_CATEGORIA = {t: c for c, tipos in CATEGORIAS_VEICULO.items() for t in tipos}


def carregar_veiculos(caminho: str | Path) -> pd.DataFrame:
    """Tabela de veículos da RENAEST (`num_acidente;tipo_veiculo;...`, o
    `tipoveiculo` bruto ou a `veiculos_acidente` exportada). Devolve uma
    linha por acidente x categoria envolvida, só com tipo conhecido."""
    bruto = _ler_csv(caminho)
    tipo = bruto["tipo_veiculo"].str.strip().str.upper()
    v = pd.DataFrame({"num_acidente": bruto["num_acidente"].astype(str), "categoria": tipo.map(_TIPO_PARA_CATEGORIA)})
    # Fica todo acidente com algum veículo de tipo conhecido, inclusive fora
    # das 4 categorias (ex.: bicicleta, `categoria` vazia): é o denominador
    # das frações em `ml.veiculos`.
    conhecido = ~tipo.isin(["", "DESCONHECIDO", "NAO INFORMADO"])
    return v[conhecido].drop_duplicates(["num_acidente", "categoria"]).reset_index(drop=True)
