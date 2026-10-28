# Arquitetura

## Visão geral

```
src/app/
  main.py            # monta o app FastAPI e registra as rotas
  core/
    config.py         # configuração (variáveis de ambiente)
    security.py         # hash de senha (bcrypt) e tokens JWT do admin
  db/
    session.py         # engine, sessão, Base declarativa
    models.py           # model ORM Sinistro
  schemas/
    sinistro.py          # schemas Pydantic (I/O da API)
    auth.py                # schema Token (resposta do login)
  services/
    adapters.py             # mapeamento por alias de coluna (schema arbitrário)
    ingestion_service.py     # decodifica, filtra, faz upsert no banco
  api/
    deps.py                    # dependência get_current_admin (protege rotas)
    routes/
      auth.py                    # POST /auth/login
      health.py                    # GET /health
      ingestion.py                   # POST /ingest/csv (protegido, admin)
      sinistros.py                     # GET /sinistros, GET /sinistros/{id}
      mapa.py                            # GET /mapa (visualização Leaflet)
scripts/
  seed_from_csv.py    # popula o banco a partir de um CSV local, sem subir o servidor
  hash_password.py      # gera o hash bcrypt para ADMIN_PASSWORD_HASH
data/
  municipio_ribeirao_preto.geojson   # contorno do município (malha IBGE)
tests/                # pytest
sinistros_12-2025.csv  # dataset bruto (estadual, ~16.8 mil linhas)
sinistros.db            # banco SQLite (gerado em runtime, fora do controle de versão)
```

## Camadas e dependências

O projeto segue uma separação simples em camadas, cada uma dependendo apenas
das camadas "abaixo" dela:

```
api/routes  →  services  →  db (models, session)
     ↓             ↓
  schemas       core (config, security)
     ↑
  api/deps  →  core (security)
```

- **`core`** não depende de nada dentro do app — é a base (configuração e,
  desde a autenticação do admin, `security.py`).
- **`db`** depende de `core` (para pegar a `DATABASE_URL`).
- **`schemas`** são contratos Pydantic independentes, usados pela camada
  `api` para validar/serializar entrada e saída.
- **`services`** contém a lógica de negócio (parsing de CSV, upsert) e
  depende de `db` (para persistir) e `core` (para saber qual município
  filtrar).
- **`api/deps`** contém dependências FastAPI reutilizáveis entre rotas —
  hoje, só `get_current_admin`, que depende de `core/security.py` para
  validar o token Bearer.
- **`api/routes`** é a camada mais externa: recebe requisições HTTP, chama
  `services` ou consulta `db` diretamente (rotas de leitura simples),
  serializa a resposta via `schemas`, e — nas rotas protegidas — declara
  `Depends(get_current_admin)` de `api/deps`.

## Fluxo de dados ponta a ponta

### 1. Ingestão

```
CSV de sinistros (qualquer schema reconhecível por alias — ver services.md)
   │
   ▼  scripts/seed_from_csv.py  OU  POST /ingest/csv
   │
services/adapters.py            — mapeia colunas por alias, campo a campo
   │
services/ingestion_service.py   — decodifica/detecta delimitador, filtra por
   │                                MUNICIPIO_ALVO (se a coluna existir),
   │                                upsert por (source_name, source_row_id)
   ▼
db (tabela `sinistros`)
```

Reingerir o mesmo arquivo é seguro: a chave de upsert é
`(source_name, source_row_id)` — o `id_sinistro` do CSV quando existe, ou um
hash do conteúdo da linha quando não existe nenhuma coluna de id (ver
[`db.md`](./db.md)) — então uma segunda ingestão apenas atualiza os
registros já existentes em vez de duplicá-los. Isso é o que permite
reingerir arquivos incrementalmente, inclusive de fontes/formatos
diferentes entre si.

### 2. Consulta (API para o time de dados)

```
GET /sinistros[?tipo_registro=&data_inicio=&data_fim=&limit=&offset=]
GET /sinistros/{id}
   │
   ▼
db.query(Sinistro) — filtros opcionais, paginação
   │
   ▼
schemas.SinistroOut — serialização para JSON
```

### 3. Visualização (mapa)

```
GET /mapa
   │
   ▼
db.query(Sinistro) — apenas registros com lat/lon não nulos
   │
   ▼
página HTML autocontida (Leaflet + OpenStreetMap via CDN)
  - contorno do município (data/municipio_ribeirao_preto.geojson)
  - camada de calor ponderada por gravidade
  - marcadores individuais coloridos por gravidade, com popup
```

Esse endpoint roda fora de qualquer sandbox de artifacts — precisa que o
navegador do usuário final tenha acesso direto à internet para baixar os
tiles do OpenStreetMap e as libs do CDN (`unpkg.com`).

### 4. Autenticação e papéis

```
POST /auth/register {username, password, name, email}
   │
   ▼
cria a conta na tabela users, sempre com role="user"


POST /auth/login {username, password}
   │
   ▼
confere o admin raiz (settings), depois a tabela users (bcrypt)
   │
   ▼
core/security.create_access_token  — JWT com o role como claim
   │
   ▼
Token {access_token, token_type: "bearer"}


GET /auth/me  (Authorization: Bearer <token>)
   └─ api/deps.get_current_user: qualquer papel, 401 se ausente/inválido

POST /ingest/csv  (Authorization: Bearer <token>)
   └─ api/deps.get_current_admin: exige role=admin, 401 sem token válido,
      403 para conta comum
```

Há dois tipos de conta: o **admin raiz**, definido em `settings` (`.env`),
e as contas comuns da tabela `users`, criadas pelo cadastro público. O papel
vai no JWT, então as rotas protegidas decidem a autorização sem consultar o
banco de novo. Hoje só `/auth/me` e `/ingest/csv` exigem token; as demais
rotas de leitura (`/sinistros`, `/risco`, `/analise`) continuam abertas.
Detalhes em [`api.md`](./api.md) e [`core.md`](./core.md).

## Por que Postgres/PostGIS

O banco padrão do projeto é Postgres (imagem `postgis/postgis`, subida via
`docker-compose.yml` — ver [`configuracao.md`](./configuracao.md)), acessado
via SQLAlchemy com o driver `psycopg`. PostGIS já vem disponível na imagem
para quando as consultas geoespaciais do modelo de predição de zonas de
risco precisarem de mais do que `latitude`/`longitude` como colunas soltas
(ex.: índices espaciais, `ST_DWithin` para vizinhança).

SQLite continua existindo no código (`db/session.py` trata o caso
`sqlite:///`), mas só como banco de teste: `tests/conftest.py` sobrescreve
`DATABASE_URL` para um arquivo SQLite temporário, mantendo a suíte rápida e
sem depender do Postgres estar no ar.

## Pendências arquiteturais conhecidas

Registradas desde a primeira versão do projeto (`README.md`):

- **Geocodificação:** parte relevante dos registros de Ribeirão Preto não
  tem latitude/longitude no CSV oficial. Ainda não há decisão tomada entre
  descartar esses registros ou geocodificá-los por logradouro — é apontado
  como crítico para o modelo de predição de zonas de risco, já que reduzir a
  amostra geograficamente enviesa o treinamento.
- **Segurança:** só `/auth/me` e `/ingest/csv` exigem token. As rotas de
  leitura (`/sinistros`, `/risco`, `/analise`) são abertas e precisam de
  proteção antes de expor a API fora da rede local.
- **Migrações:** o schema é criado via `Base.metadata.create_all` (ver
  [`db.md`](./db.md)); não há Alembic configurado. Qualquer mudança de
  schema em produção exigirá migração manual até isso ser resolvido.
- **PostGIS ainda não é usado de fato:** a imagem `postgis/postgis` está no
  ar e a extensão pode ser habilitada (`CREATE EXTENSION postgis;`), mas os
  models ORM continuam usando `latitude`/`longitude` como `Float` soltos —
  migrar para um tipo `geometry` (via `GeoAlchemy2`, por exemplo) fica para
  quando as consultas espaciais do modelo de risco precisarem disso.
- **Branch `ml-zonas-risco` não publicada:** os commits da carga do InfoSiga,
  das rotas `/analise` e das páginas Explorar/Ficha/Comparar/Dados existem
  só localmente. A máquina de desenvolvimento não tem chave SSH válida para o
  GitHub e a branch não tem upstream. Falta configurar o acesso e rodar
  `git push -u origin ml-zonas-risco`.
- **Autoria do modelo de ocorrência:** [`ml.md`](./ml.md) cita o
  `modelo_risco_acidentes_v3.py` "do time de ML", mas o original não está no
  repositório e a autoria não está registrada. Falta identificar o autor e
  versionar ou referenciar o arquivo de origem.
- **Guia de Integração desatualizado:** `docs/apresentacao/Guia_Integracao_Frontend.pdf`
  ainda diz que a autenticação é single-user e que os endpoints não têm
  autenticação. Precisa ser regerado a partir da fonte, que não está no
  repositório. Os PDFs de `docs/apresentacao/` também seguem sem versionar.
