"""Previsão por tipo de veículo envolvido (filtro "Veículo" do mapa).

Para cada célula, a fração dos acidentes que envolvem cada categoria
(moto, carro, caminhão, ônibus), calculada só entre os acidentes com tipo
de veículo informado e suavizada em direção à fração da cidade. Multiplicada
pela previsão da célula, dá os acidentes previstos envolvendo aquela
categoria.

Supõe que os acidentes sem tipo informado têm a mesma composição dos
informados: desde 2023 o tipo vem em 55% (2023), 61% (2024) e ~1/3 (2025-26)
dos acidentes. Um acidente pode envolver mais de uma categoria (moto x
carro), então as frações de uma célula somam mais de 1.
"""

from __future__ import annotations

import pandas as pd

from ml.dados import CATEGORIAS_VEICULO
from ml.ocorrencia import _niveis

K_SUAVIZACAO = 20.0   # em acidentes com tipo conhecido


def por_celula(g: pd.DataFrame, veiculos: pd.DataFrame, celulas: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    conhecidos = set(veiculos["num_acidente"])
    gc = g[g["num_acidente"].astype(str).isin(conhecidos)].assign(num_acidente=lambda d: d["num_acidente"].astype(str))
    n_conhecido = gc.groupby("celula")["w"].sum()

    linhas, frac_cidade = [], {}
    for categoria in CATEGORIAS_VEICULO:
        envolvidos = set(veiculos.loc[veiculos["categoria"] == categoria, "num_acidente"])
        n_cat = gc[gc["num_acidente"].isin(envolvidos)].groupby("celula")["w"].sum()
        cidade = float(n_cat.sum() / max(n_conhecido.sum(), 1e-9))
        frac_cidade[categoria] = cidade
        fracao = ((n_cat.reindex(celulas.index).fillna(0) + K_SUAVIZACAO * cidade)
                  / (n_conhecido.reindex(celulas.index).fillna(0) + K_SUAVIZACAO))
        esperado = celulas["acidentes_esperados"] * fracao
        linhas.append(pd.DataFrame({"celula": celulas.index, "veiculo": categoria, "fracao": fracao.to_numpy(),
                                    "acidentes_esperados": esperado.to_numpy(),
                                    "nivel_risco": _niveis(esperado).to_numpy()}))
    resumo = {"cobertura_tipo_veiculo": float(gc["w"].sum() / max(g["w"].sum(), 1e-9)),
              "fracao_cidade": frac_cidade}
    return pd.concat(linhas, ignore_index=True), resumo
