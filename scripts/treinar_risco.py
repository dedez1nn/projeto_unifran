"""Treina os modelos de risco e publica o resultado no banco da API.

Lê a base RENAEST de Ribeirão Preto (CSV bruto da Senatran ou a tabela
`acidentes_tratados` exportada), roda o pipeline de `src/ml/` e substitui o
conteúdo das tabelas `risco_*` lidas por `GET /risco/...`. Também salva os
CSVs e as métricas em `--saida` para conferência.

A tabela de veículos (`--veiculos`, padrão `data/tipoveiculo_ribeirao_preto.csv`
se existir) é opcional e alimenta o filtro "Veículo" do mapa.

Uso: python scripts/treinar_risco.py [--csv data/acidentes_ribeirao_preto.csv]
                                      [--veiculos data/tipoveiculo_ribeirao_preto.csv]
                                      [--saida data/ml_saidas] [--sem-publicar]
Dependências: requirements-ml.txt
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ml.publicar import publicar  # noqa: E402
from ml.treino import salvar_em_disco, treinar  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--csv", default=str(ROOT / "data" / "acidentes_ribeirao_preto.csv"))
    padrao_veiculos = ROOT / "data" / "tipoveiculo_ribeirao_preto.csv"
    ap.add_argument("--veiculos", default=str(padrao_veiculos) if padrao_veiculos.exists() else None)
    ap.add_argument("--saida", default=str(ROOT / "data" / "ml_saidas"))
    ap.add_argument("--sem-publicar", action="store_true", help="só treina e salva em disco")
    args = ap.parse_args()

    resultado = treinar(args.csv, args.veiculos)
    salvar_em_disco(resultado, args.saida)
    print(f"Arquivos salvos em {Path(args.saida).resolve()}")
    if not args.sem_publicar:
        execucao = publicar(resultado)
        print(f"Publicado no banco (execução #{execucao.id}, {execucao.gerado_em:%Y-%m-%d %H:%M}).")


if __name__ == "__main__":
    main()
