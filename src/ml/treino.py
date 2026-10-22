"""Pipeline completo: carga -> backtest -> ranking -> tendência -> pontos
críticos -> perfil horário -> série mensal. Devolve um `ResultadoTreino`
pronto para `ml.publicar.publicar` (ou para salvar em disco).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ml import ocorrencia, perfil, pontos_criticos, serie_mensal, tendencia, veiculos
from ml.dados import carregar_acidentes, carregar_veiculos, diagnostico_qualidade
from ml.publicar import ResultadoTreino


def _registros(df: pd.DataFrame) -> list[dict]:
    return df.round(4).reset_index().to_dict(orient="records")


def treinar(caminho_csv: str | Path, caminho_veiculos: str | Path | None = None, log=print) -> ResultadoTreino:
    """`caminho_veiculos` é opcional: sem ele, o filtro de veículo do mapa
    simplesmente não aparece."""
    df = carregar_acidentes(caminho_csv)
    log(f"Registros (2019+): {len(df)} | {df.data_acidente.min().date()} a {df.data_acidente.max().date()}")
    qualidade = diagnostico_qualidade(df, ocorrencia.BBOX)

    base = ocorrencia.preparar_geo(df)
    log(f"[Geo] {base.resumo}")

    media, por_origem, testes = ocorrencia.backtest_rolling(base)
    modelo = ocorrencia.escolher_modelo(media)
    log("[Ocorrência] backtest (média dos cortes):\n" + media.round(3).to_string())
    log(f">> modelo escolhido (menor desvio de Poisson): {modelo}")

    celulas, vias, g = ocorrencia.gerar_ranking(base, modelo)
    alta = tendencia.zonas_em_alta(g, base.ultimo_mes)
    celulas = celulas.join(alta[["tendencia_razao", "em_alta"]])
    celulas["em_alta"] = celulas["em_alta"].fillna(False).astype(bool)
    log(f"[Ranking] {len(celulas)} células, {len(vias)} vias, {int(celulas.em_alta.sum())} em alta; "
        f"previsão {celulas.janela_previsao.iloc[0]}")

    por_veiculo, resumo_veiculos = pd.DataFrame(columns=["celula", "veiculo", "fracao", "acidentes_esperados",
                                                         "nivel_risco"]), None
    if caminho_veiculos:
        por_veiculo, resumo_veiculos = veiculos.por_celula(g, carregar_veiculos(caminho_veiculos), celulas)
        log(f"[Veículos] tipo informado em {resumo_veiculos['cobertura_tipo_veiculo']:.0%} dos acidentes "
            f"desde 2023; fração na cidade: {resumo_veiculos['fracao_cidade']}")

    pontos = pontos_criticos.pontos_criticos(base.validos)
    log(f"[Pontos críticos] {len(pontos)} aglomerados de acidentes com óbito")

    perfis = perfil.perfis(df, vias.index)
    serie = serie_mensal.serie_observada(df)
    avaliacao_serie = serie_mensal.avaliar(serie)
    log(f"[Série mensal] {avaliacao_serie}")

    metricas = {
        "ocorrencia_backtest": _registros(media),
        "ocorrencia_por_corte": por_origem.round(4).to_dict(orient="records"),
        "obitos_por_ordenacao": _registros(ocorrencia.avaliar_indice_obitos(testes)),
        "gravidade_por_horario": ocorrencia.avaliar_gravidade_por_horario(df),
        "serie_mensal": avaliacao_serie,
        "quantis_taxa_hora": perfil.quantis_taxa_hora(perfis, vias),
        "fracao_alto": ocorrencia.FRACAO_ALTO,
        "fracao_medio": ocorrencia.FRACAO_MEDIO,
        "qualidade_por_ano": _registros(qualidade.rename_axis("ano")),
        "veiculos": resumo_veiculos,
    }
    return ResultadoTreino(
        celulas=celulas, celulas_veiculo=por_veiculo, vias=vias, perfil=perfis, pontos_criticos=pontos,
        previsao_mensal=serie_mensal.prever(serie), fonte=Path(caminho_csv).name,
        modelo_ocorrencia=modelo, janela_previsao=celulas.janela_previsao.iloc[0],
        tamanho_celula=ocorrencia.TAMANHO_CELULA, metricas=metricas, resumo_limpeza=base.resumo,
    )


def salvar_em_disco(r: ResultadoTreino, saida: str | Path) -> None:
    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    r.celulas.to_csv(saida / "ranking_celulas.csv")
    r.vias.to_csv(saida / "ranking_vias.csv")
    r.celulas_veiculo.to_csv(saida / "ranking_celulas_veiculo.csv", index=False)
    r.perfil.to_csv(saida / "perfil_horario.csv", index=False)
    r.pontos_criticos.to_csv(saida / "pontos_criticos.csv", index=False)
    r.previsao_mensal.to_csv(saida / "previsao_mensal.csv", index=False)
    pd.Series(r.metricas, dtype=object).to_json(saida / "metricas.json", force_ascii=False, indent=2)
