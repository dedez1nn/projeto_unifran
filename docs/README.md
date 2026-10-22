# Documentação do projeto

**Inteligência Artificial Aplicada à Predição de Zonas de Risco em Sinistros
de Trânsito: Estudo de Caso em Ribeirão Preto-SP.**

Back-end em Python (FastAPI + SQLAlchemy/SQLite) responsável por ingerir os
dados oficiais de sinistros de trânsito, restringi-los ao município de
Ribeirão Preto-SP, disponibilizá-los via API para o time de análise de dados
e oferecer uma visualização geográfica (mapa de calor) dos registros.

Esta pasta documenta o projeto **pasta por pasta, arquivo por arquivo**. Cada
documento cobre um diretório do repositório; dentro dele, cada arquivo
relevante tem sua própria seção.

## Índice

| Documento | Conteúdo |
|---|---|
| [`arquitetura.md`](./arquitetura.md) | Visão geral: como as pastas se encaixam, fluxo de dados ponta a ponta |
| [`core.md`](./core.md) | `src/app/core/` — configuração da aplicação |
| [`db.md`](./db.md) | `src/app/db/` — conexão com o banco e modelo ORM |
| [`schemas.md`](./schemas.md) | `src/app/schemas/` — contratos de entrada/saída da API |
| [`services.md`](./services.md) | `src/app/services/` — parsing do CSV e lógica de ingestão |
| [`api.md`](./api.md) | `src/app/api/routes/` — endpoints HTTP |
| [`api.md`](./api.md#analisepy) | também `/analise/...`: exploração, perfil das vítimas, qualidade dos dados e comparação entre cidades |
| [`ml.md`](./ml.md) | `src/ml/` e `scripts/treinar_risco.py`: modelos de risco (zonas, vias, pontos críticos, série mensal) |
| [`main.md`](./main.md) | `src/app/main.py` — montagem da aplicação FastAPI |
| [`scripts.md`](./scripts.md) | `scripts/` — utilitário de seed do banco |
| [`tests.md`](./tests.md) | `tests/` — suíte de testes automatizados |
| [`dados.md`](./dados.md) | `data/`, `sinistros_12-2025.csv`, `sinistros.db` — os dados em si |
| [`configuracao.md`](./configuracao.md) | Arquivos de raiz: `requirements*.txt`, `.gitignore`, variáveis de ambiente |

## Como rodar localmente

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

# subir o Postgres (postgis/postgis, via docker-compose.yml)
cp .env.example .env
docker compose up -d db

# popular o banco com o CSV local (bootstrap)
.venv/bin/python scripts/seed_from_csv.py

# subir a API
.venv/bin/uvicorn app.main:app --app-dir src --reload
# docs interativas (Swagger) em http://127.0.0.1:8000/docs
# mapa navegável em http://127.0.0.1:8000/mapa

# carregar o histórico do InfoSiga (zip estadual em data/)
.venv/bin/python scripts/carregar_infosiga.py

# treinar e publicar os modelos de risco (base RENAEST em data/)
.venv/bin/python scripts/treinar_risco.py
```

Rodar os testes:

```bash
.venv/bin/pytest
```
