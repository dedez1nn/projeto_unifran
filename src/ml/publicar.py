"""Grava o resultado de um treino nas tabelas que a API lê.

Substitui o conteúdo inteiro das tabelas de risco numa única transação: quem
consulta a API vê a versão anterior completa ou a nova completa, nunca uma
mistura das duas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from app.db.models import (
    MlExecucao,
    RiscoCelula,
    RiscoCelulaVeiculo,
    RiscoPerfilHorario,
    RiscoPontoCritico,
    RiscoPrevisaoMensal,
    RiscoVia,
)
from app.db.session import Base, SessionLocal, engine

_TABELAS = (RiscoCelula, RiscoCelulaVeiculo, RiscoVia, RiscoPerfilHorario, RiscoPontoCritico, RiscoPrevisaoMensal)


@dataclass
class ResultadoTreino:
    celulas: pd.DataFrame
    celulas_veiculo: pd.DataFrame   # vazio quando o treino não recebeu a tabela de veículos
    vias: pd.DataFrame
    perfil: pd.DataFrame
    pontos_criticos: pd.DataFrame
    previsao_mensal: pd.DataFrame
    fonte: str
    modelo_ocorrencia: str
    janela_previsao: str
    tamanho_celula: float
    metricas: dict
    resumo_limpeza: dict


def _limpo(valor):
    """NaN/numpy -> tipos que o banco e o JSON aceitam."""
    if valor is None:
        return None
    if hasattr(valor, "item"):
        valor = valor.item()
    if isinstance(valor, float) and math.isnan(valor):
        return None
    return valor


def _linhas(df: pd.DataFrame) -> list[dict]:
    return [{k: _limpo(v) for k, v in linha.items()} for linha in df.to_dict(orient="records")]


def _celulas(r: ResultadoTreino) -> list[RiscoCelula]:
    c = r.celulas.reset_index()
    return [RiscoCelula(
        celula=x["celula"], lat=x["lat"], lon=x["lon"], tamanho=r.tamanho_celula,
        acidentes_esperados=x["acidentes_esperados"], acidentes_12m=x["n_12"],
        acidentes_historico=x["n_total"], obitos_historico=x["n_obitos"],
        nivel_risco=x["nivel_risco"], rua_principal=x["rua_principal"],
        tendencia_razao=x["tendencia_razao"], em_alta=bool(x["em_alta"]),
        janela_previsao=x["janela_previsao"],
    ) for x in _linhas(c)]


def _vias(r: ResultadoTreino) -> list[RiscoVia]:
    v = r.vias.reset_index()
    return [RiscoVia(via=x["rua"], acidentes_esperados=x["acidentes_esperados"],
                     acidentes_historico=x["n_total"], nivel_risco=x["nivel_risco"],
                     lat=x["lat"], lon=x["lon"]) for x in _linhas(v)]


def publicar(r: ResultadoTreino) -> MlExecucao:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for tabela in _TABELAS:
            db.query(tabela).delete()
        db.add_all(_celulas(r))
        db.add_all(_vias(r))
        db.bulk_insert_mappings(RiscoCelulaVeiculo, _linhas(r.celulas_veiculo))
        db.bulk_insert_mappings(RiscoPerfilHorario, _linhas(r.perfil))
        db.add_all(RiscoPontoCritico(**x) for x in _linhas(r.pontos_criticos))
        db.add_all(RiscoPrevisaoMensal(**x) for x in _linhas(r.previsao_mensal))
        execucao = MlExecucao(fonte=r.fonte, modelo_ocorrencia=r.modelo_ocorrencia,
                              janela_previsao=r.janela_previsao, metricas=r.metricas,
                              resumo_limpeza=r.resumo_limpeza)
        db.add(execucao)
        db.commit()
        db.refresh(execucao)
        return execucao
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
