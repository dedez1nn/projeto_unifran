Estamos desenvolvendo um projeto que é voltado para

"Inteligência Artificial Aplicada à Predição de Zonas de Risco em Sinistros de Trânsito: Estudo de Caso em Ribeirão Preto-SP"

A plataforma será desenvolvida em Python e estamos aqui focados em Back-end, por isso, desenvolva a arquitetura inicial para digestão desses dados no csv no diretório.

## Escopo

Dados restritos ao município de **Ribeirão Preto-SP**. O CSV de origem é estadual (todo SP); o filtro é aplicado na ingestão.

## Arquitetura

API de ingestão (FastAPI) + armazenamento (Postgres/PostGIS via SQLAlchemy, subido com Docker Compose) para que o time de análise de dados consuma os sinistros via HTTP conforme novos arquivos forem chegando. Reingerir o mesmo arquivo é seguro (upsert por `id_sinistro`, idempotente).

A própria API também serve o frontend (HTML/CSS/JS estático, sem build) em
`/` — subindo só o backend já dá para abrir o site completo (login,
cadastro, dashboard, mapa, simulação de risco) no navegador, sem precisar de
um segundo processo/servidor.

```
src/app/
  main.py            # app FastAPI (inclui os routers e monta frontend/ em "/")
  core/config.py     # configuração (DATABASE_URL, MUNICIPIO_ALVO)
  db/                # models SQLAlchemy + sessão
  schemas/           # schemas Pydantic (I/O da API)
  services/
    csv_parser.py     # parsing do CSV oficial (encoding latin-1, tipos)
    ingestion_service.py  # upsert no banco
  api/routes/        # endpoints (auth, health, ingest, mapa, sinistros)
frontend/            # site estático (login/cadastro, dashboard, mapa, simulação de risco)
scripts/seed_from_csv.py  # popula o banco a partir de um CSV local, sem subir o servidor
docker-compose.yml   # sobe o Postgres (postgis/postgis) usado pela API
tests/               # pytest (backend) + frontend/tests/logic.test.js (roda com `node`, sem framework)
```

## Rodando localmente

### Com Docker (recomendado)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

# subir o Postgres
cp .env.example .env
docker compose up -d db

# popular o banco com o CSV local (bootstrap)
.venv/bin/python scripts/seed_from_csv.py

# subir a API
.venv/bin/uvicorn app.main:app --app-dir src --reload
# site completo em http://127.0.0.1:8000/ · docs interativas em http://127.0.0.1:8000/docs
```

### Sem Docker (fallback com SQLite)

Sem Docker disponível, a API roda do mesmo jeito trocando o banco para
SQLite — não há uso de recursos específicos do PostGIS no código hoje, e é o
mesmo banco que os testes (`tests/conftest.py`) já usam.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

cp .env.example .env
# no .env, trocar DATABASE_URL por um arquivo SQLite local, ex.:
# DATABASE_URL=sqlite:///./sinistros.db

# popular o banco com o CSV local (bootstrap)
.venv/bin/python scripts/seed_from_csv.py

# subir a API
.venv/bin/uvicorn app.main:app --app-dir src --reload
# site completo em http://127.0.0.1:8000/ · docs interativas em http://127.0.0.1:8000/docs
```

As tabelas são criadas automaticamente (`Base.metadata.create_all`, sem
migrações), então nenhum passo extra é necessário além de apontar
`DATABASE_URL` para o arquivo SQLite. O arquivo `.db` gerado já está no
`.gitignore`.

Endpoints principais:
- `POST /auth/register`: cadastro público de conta (username/password/nome/e-mail), sempre com papel `user`
- `POST /auth/login`: autentica (admin raiz via `.env` ou conta cadastrada) e retorna um token Bearer
- `GET /auth/me`: identidade do usuário do token atual (usado pelo frontend para montar a sessão)
- `POST /ingest/csv`: upload de um CSV no formato oficial (multipart/form-data, campo `file`), restrito a `role=admin`
- `GET /sinistros`: lista paginada, com filtros por atributo e bounding box geográfica
- `GET /sinistros/geojson`: os mesmos filtros, em GeoJSON, para o frontend desenhar o mapa
- `GET /sinistros/opcoes`: valores distintos da base, para popular os filtros do frontend
- `GET /sinistros/{id}`: detalhe de um sinistro
- `GET /mapa`: mapa Leaflet pronto (calor por gravidade), renderizado no servidor
- `GET /risco/...`: modelos de risco publicados (zonas previstas, vias, pontos críticos, previsão mensal, simulação por via/dia/hora); ver [`docs/ml.md`](docs/ml.md)
- `GET /health`

## Modelos de risco

Treinados offline a partir da base RENAEST de Ribeirão Preto
(`data/acidentes_ribeirao_preto.csv` e, opcionalmente,
`data/tipoveiculo_ribeirao_preto.csv` para o filtro por veículo) e publicados no banco, de onde a API
os serve em `/risco/...` e o site os consome (mapa, alertas, simulação,
previsão mensal):

```bash
.venv/bin/pip install -r requirements-ml.txt   # já incluso em requirements-dev.txt
.venv/bin/python scripts/treinar_risco.py
```

Método, backtest e limitações em [`docs/ml.md`](docs/ml.md).

## Próximos passos conhecidos

- Decidir estratégia para os ~69% dos registros de Ribeirão Preto sem latitude/longitude (descartar vs. geocodificar por logradouro) — crítico para o modelo de zonas de risco.
- Autenticação/autorização nos endpoints antes de expor fora da rede local.
- Migrações de schema (Alembic) quando o CSV oficial mudar de formato.
- Avaliar Postgres+PostGIS se as consultas geoespaciais para o modelo de risco exigirem mais do que SQLite oferece.
