# `src/app/db/`

Camada de acesso a dados: conexão com o banco e os modelos ORM do projeto
(`Sinistro` e `User`).

## `session.py`

```python
connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- **`engine`** — criado a partir de `settings.database_url` (ver
  [`core.md`](./core.md)), que por padrão aponta para o Postgres subido pelo
  `docker-compose.yml`. O `connect_args={"check_same_thread": False}` só é
  aplicado quando o banco é SQLite: é necessário porque o SQLite por padrão
  proíbe usar a mesma conexão em threads diferentes, e o FastAPI/uvicorn
  atende requisições em threads diferentes por padrão. Para Postgres esse
  `connect_args` fica vazio — a checagem `startswith("sqlite")` continua
  existindo porque os testes (`tests/conftest.py`) usam SQLite para ficarem
  rápidos e isolados, então o código precisa suportar os dois bancos.
- **`SessionLocal`** — factory de sessões SQLAlchemy, com `autocommit=False`
  e `autoflush=False` (padrão explícito, controle total sobre quando
  commitar/flushar).
- **`Base`**: classe declarativa da qual todo model ORM herda (`Sinistro` e
  `User`, ver `models.py` abaixo). É contra `Base.metadata` que
  `create_all` é chamado em `main.py` para criar as tabelas.
- **`get_db()`** — generator usado como dependência do FastAPI
  (`Depends(get_db)`) nas rotas que precisam do banco. Garante que a sessão
  é sempre fechada (`finally: db.close()`) mesmo se a rota levantar exceção.

## `models.py`

Define dois models: `Sinistro` (tabela `sinistros`) e `User` (tabela
`users`).

### `User`

```python
ROLE_ADMIN = "admin"
ROLE_USER = "user"

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=ROLE_USER)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
```

Conta criada via `POST /auth/register` (ver [`api.md`](./api.md)). Sempre
nasce com `role="user"`: o endpoint de cadastro não aceita esse campo na
entrada, então não existe caminho para um cadastro público virar admin.
`username` tem `unique=True`: uma segunda tentativa de cadastro com o mesmo
nome (ou com o mesmo valor de `ADMIN_USERNAME`) recebe `409 Conflict` antes
mesmo de chegar ao banco (checado explicitamente em `api/routes/auth.py`).

O **admin raiz** (usado para liberar `POST /ingest/csv`) continua fora dessa
tabela, vindo de `ADMIN_USERNAME`/`ADMIN_PASSWORD_HASH` (ver
[`core.md`](./core.md)). `User` só existe para as contas de papel `user`
que se autenticam mas não têm permissão de importar dados. Ver
[`core.md`](./core.md#securitypy) para como o papel (`role`) vira um claim
no JWT.

### `Sinistro`

```python
class Sinistro(Base):
    __tablename__ = "sinistros"
    __table_args__ = (UniqueConstraint("source_name", "source_row_id", ...),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_name: Mapped[str] = mapped_column(String(50), index=True)
    source_row_id: Mapped[str] = mapped_column(String(120), index=True)
    id_sinistro: Mapped[int | None] = mapped_column(Integer, index=True)
    ...
```

### Por que a PK não é `id_sinistro`

A ingestão aceita CSVs de fontes heterogêneas (ver
[`services.md`](./services.md)) — nem todo formato tem um `id_sinistro`
confiável (o oficial INFOSIGA tem; outros não). Por isso a PK é um `id`
autoincremento (surrogate, sem significado de negócio) e a chave usada para
**upsert idempotente** é `(source_name, source_row_id)`: `source_name` é
derivado do **nome do arquivo** (`_source_name_from_filename` em
`services/ingestion_service.py`), não uma constante fixa — cada arquivo é
seu próprio namespace, de propósito: evita que um `id_sinistro`/id nativo
que coincida por acaso entre dois arquivos de fontes diferentes seja tratado
como "a mesma linha" e sobrescreva o sinistro errado. `source_row_id` é a
chave natural que o parser extraiu daquela linha — o `id_sinistro` do CSV
quando existe, ou um hash SHA-1 do conteúdo bruto da linha quando não existe
nenhuma coluna de id reconhecível. `id_sinistro` continua existindo como
coluna comum (nullable, preenchida quando a fonte o declara), só deixou de
ser PK.

### Grupos de colunas

| Grupo | Colunas (exemplos) | Observação |
|---|---|---|
| Identificação/registro | `id_sinistro`, `tipo_registro` | `tipo_registro` distingue tipos de registro do boletim |
| Data/hora | `data_sinistro`, `ano_sinistro`, `mes_sinistro`, `dia_sinistro`, `hora_sinistro`, `ano_mes_sinistro`, `dia_da_semana`, `turno` | Campos redundantes com `data_sinistro`/`hora_sinistro`, mas mantidos porque já vêm prontos do CSV oficial (evita recalcular) |
| Localização | `logradouro`, `numero_logradouro`, `tipo_via`, `tipo_local`, `latitude`, `longitude`, `cod_ibge`, `municipio`, `regiao_administrativa`, `administracao`, `conservacao`, `circunscricao` | `municipio` é indexado (`index=True`) — é o principal filtro de ingestão e consulta |
| Classificação do sinistro | `tp_sinistro_primario` | Tipo primário textual (ex.: "COLISAO") |
| Veículos envolvidos | `qtd_pedestre`, `qtd_bicicleta`, `qtd_motocicleta`, `qtd_automovel`, `qtd_onibus`, `qtd_caminhao`, `qtd_veic_outros`, `qtd_veic_nao_disponivel` | Contagens inteiras, todas opcionais |
| Gravidade das vítimas | `qtd_gravidade_fatal`, `qtd_gravidade_grave`, `qtd_gravidade_leve`, `qtd_gravidade_ileso`, `qtd_gravidade_nao_disponivel` | Usadas para colorir/ponderar o mapa de calor — ver [`api.md`](./api.md) |
| Tipo de sinistro (flags) | `tp_sinistro_atrop_pedestre`, `tp_sinistro_colisao_frontal`, `tp_sinistro_colisao_traseira`, `tp_sinistro_capotamento`, `tp_sinistro_tombamento`, etc. | Booleanas, `default=False`; o CSV oficial as codifica como `"S"`/vazio (ver `services/adapters.py`) |
| Proveniência | `id` (PK), `source_name`, `source_row_id`, `raw_data`, `source_file`, `ingested_at` | `id`/`source_name`/`source_row_id` ver seção acima. `raw_data` (JSON) guarda a linha crua inteira, mapeada ou não — nenhum dado do CSV-fonte se perde. `source_file`/`ingested_at` rastreiam de qual arquivo e quando cada linha veio |

Todas as colunas de dado (fora `id`, `source_name`, `source_row_id`) são
opcionais (`| None`), refletindo que fontes diferentes trazem subconjuntos
diferentes de campos.

### Criação de tabelas

Não há migrações (Alembic). As tabelas são criadas via
`Base.metadata.create_all(bind=engine)`, chamado tanto em `main.py` (ao subir
a API) quanto em `scripts/seed_from_csv.py` (ao rodar o seed
standalone). Qualquer mudança de schema em uma base já populada exige
intervenção manual — ver pendências em [`arquitetura.md`](./arquitetura.md).

### Tabelas dos modelos de risco

Publicadas por `scripts/treinar_risco.py` (ver [`ml.md`](./ml.md)) e só
lidas pela API. Cada publicação substitui o conteúdo inteiro delas numa
transação.

| Model | Tabela | Uma linha por |
|---|---|---|
| `RiscoCelula` | `risco_celulas` | célula de ~550 m: previsão de 12 meses, nível, rua principal, tendência (`em_alta`, `tendencia_razao`) |
| `RiscoCelulaVeiculo` | `risco_celulas_veiculo` | célula x categoria de veículo: fração dos acidentes, previsão e nível para a categoria |
| `RiscoVia` | `risco_vias` | via do ranking: previsão de 12 meses, histórico, nível, centróide |
| `RiscoPerfilHorario` | `risco_perfil_horario` | escopo (via ou `__cidade__`) x dia da semana x hora, com a fração dos acidentes |
| `RiscoPontoCritico` | `risco_pontos_criticos` | aglomerado de acidentes com óbito |
| `RiscoPrevisaoMensal` | `risco_previsao_mensal` | mês: real (histórico) ou previsto com intervalo (futuro) |
| `MlExecucao` | `ml_execucoes` | publicação: modelo escolhido, métricas (JSON) e resumo da limpeza; guarda o histórico |

São tabelas novas, então `Base.metadata.create_all` as cria sozinho em
bancos já existentes, sem migração.

### Dados analíticos do InfoSiga

Preenchidos por `scripts/carregar_infosiga.py`:

| Model | Tabela | Uma linha por |
|---|---|---|
| `Pessoa` | `pessoas` | pessoa envolvida num sinistro de Ribeirão Preto: idade, faixa etária, sexo, tipo de vítima, meio de transporte, gravidade. Liga a `Sinistro` por `id_sinistro` |
| `IndicadorMunicipio` | `indicadores_municipios` | município de SP x ano: sinistros, fatais, notificações, óbitos, feridos e população do IBGE (só os totais, não as 1,4 milhão de linhas do estado) |

`Sinistro.coordenada_generica` marca a coordenada usada por 20 ou mais
sinistros de 10 ou mais endereços diferentes: a posição padrão do
geocodificador, não o local do sinistro (no InfoSiga de Ribeirão Preto, 893
sinistros em 8 pontos; um deles concentra 324 sinistros de 265 endereços).
A coordenada original é mantida. Coluna nova em tabela existente:
`sync_missing_columns` a adiciona sozinho.
