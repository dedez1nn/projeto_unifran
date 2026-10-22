"""Carrega o histórico do InfoSiga (zip estadual, 2015-2026) no banco da API.

Ingere os sinistros e as pessoas envolvidas de Ribeirão Preto e grava os
indicadores anuais de todos os municípios de SP (com a população do IBGE de
`data/populacao_municipios_sp.csv`) para a comparação entre cidades. Pode ser
rodado de novo a cada zip novo: a ingestão é idempotente e as demais tabelas
são substituídas.

Uso: python scripts/carregar_infosiga.py [--zip data/dados_infosiga.zip]
                                          [--populacao data/populacao_municipios_sp.csv]
Dependências: requirements-ml.txt (pandas)
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.db.models import IndicadorMunicipio, Pessoa  # noqa: E402,F401 - registra as tabelas
from app.db.session import Base, SessionLocal, engine, sync_missing_columns  # noqa: E402
from etl import infosiga  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--zip", default=str(ROOT / "data" / "dados_infosiga.zip"))
    ap.add_argument("--populacao", default=str(ROOT / "data" / "populacao_municipios_sp.csv"))
    args = ap.parse_args()

    Base.metadata.create_all(bind=engine)
    sync_missing_columns()  # bancos criados antes de `sinistros.coordenada_generica`
    db = SessionLocal()
    try:
        resumos, duplicados = infosiga.carregar_sinistros(db, args.zip)
        for r in resumos:
            print(f"[sinistros] {r.source_file}: {r.inserted} novos, {r.updated} atualizados, "
                  f"{r.skipped_invalid} inválidos")
        if duplicados:
            print(f"[sinistros] {duplicados} linhas de outros arquivos do InfoSiga removidas "
                  "(o mesmo sinistro já veio na série completa)")
        print(f"[sinistros] {infosiga.marcar_coordenadas_genericas(db)} sinistros em coordenada genérica do "
              "geocodificador (ficam fora do mapa e dos recortes geográficos)")
        print(f"[pessoas] {infosiga.carregar_pessoas(db, args.zip)} pessoas envolvidas")
        print(f"[municípios] {infosiga.carregar_indicadores(db, args.zip, args.populacao)} linhas município x ano")
    finally:
        db.close()


if __name__ == "__main__":
    main()
