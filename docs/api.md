# `src/app/api/routes/`

Camada HTTP: cada arquivo é um `APIRouter` registrado em
[`main.py`](./main.md). As rotas de escrita/leitura simples (`ingestion.py`,
`sinistros.py`) delegam a lógica para `services`/`db`; `mapa.py` monta e
devolve HTML diretamente.

## `auth.py`

Prefixo `/auth`, tag `auth`. Cadastro e login de contas.

### `POST /auth/register`

Cadastro público, sem autenticação. Recebe JSON
([`UserCreate`](./schemas.md): `username`, `password`) e devolve o
[`UserOut`](./schemas.md) criado (`201 Created`). Sempre cria a conta com
`role="user"`: não há como o corpo da requisição pedir `role="admin"`,
o schema de entrada nem tem esse campo.

`409 Conflict` (`"Nome de usuário já em uso"`) se o `username` já existir na
tabela `users` **ou** coincidir com `settings.admin_username`. Isso evita uma
conta cadastrada ficar "encoberta" pelo admin raiz (o login sempre confere o
admin raiz primeiro, ver abaixo).

### `POST /auth/login`

Recebe `application/x-www-form-urlencoded` (`OAuth2PasswordRequestForm`:
campos `username`/`password` — não JSON) e devolve um
[`Token`](./schemas.md) (`access_token` + `token_type: "bearer"`).

Confere as credenciais em duas etapas:
1. Contra o **admin raiz** (`settings.admin_username`/
   `settings.admin_password_hash`, ver [`core.md`](./core.md)): se bater,
   emite um token com `role="admin"`.
2. Senão, contra a tabela `users` (contas de `POST /auth/register`): se
   bater, emite um token com o `role` gravado naquela conta (`"user"`, hoje
   o único papel que o cadastro público produz).

`401 Unauthorized` se nenhuma das duas bater. `verify_password`/
`create_access_token` estão em `app/core/security.py`, ver
[`core.md`](./core.md).

O token é um JWT assinado com `settings.jwt_secret_key`, válido por
`settings.access_token_expire_minutes` (padrão 60min), com o papel
(`role`) embutido como claim. Usado como `Authorization: Bearer <token>`
nas rotas protegidas. `POST /ingest/csv` exige especificamente `role=admin`
(`api/deps.get_current_admin`, ver abaixo), então uma conta cadastrada via
`POST /auth/register` se autentica normalmente mas recebe `403 Forbidden` ao
tentar importar CSV.

## `health.py`

```python
@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

Healthcheck trivial, sem dependência de banco — útil para checagens de
liveness de infraestrutura sem gerar carga na base.

## `ingestion.py`

Prefixo `/ingest`, tag `ingestion`.

### `POST /ingest/csv`

**Protegido:** exige `Authorization: Bearer <token>` válido (obtido em
`POST /auth/login`) via `Depends(get_current_admin)` — sem token válido,
`401 Unauthorized` antes de qualquer leitura do arquivo. Ver
[`api/deps.py`](#depspy) abaixo.

Recebe um upload `multipart/form-data` (campo `file`) com um CSV de
sinistros — **qualquer schema reconhecível** pelo mapeamento por-alias em
`services/adapters.py`, não só o formato oficial INFOSIGA — e devolve um
[`IngestionSummary`](./schemas.md).

- Valida que o arquivo enviado tem extensão `.csv` (case-insensitive);
  senão, `400 Bad Request` com `"O arquivo enviado deve ser .csv"`.
- Lê o corpo do upload (`await file.read()`) e delega inteiramente para
  `services.ingestion_service.ingest_csv_bytes` — ver
  [`services.md`](./services.md) para o que acontece (detecção de
  encoding/delimitador, mapeamento por alias, filtro por município quando a
  coluna existe, upsert por `(source_name, source_row_id)`).
- **Idempotente por design:** reenviar o mesmo arquivo atualiza os registros
  existentes em vez de duplicá-los, pensado para o time de dados poder
  alimentar a base incrementalmente conforme novos arquivos (de qualquer
  fonte) chegam.
- Nenhuma linha derruba o arquivo inteiro: colunas não reconhecidas e
  valores malformados viram avisos no `IngestionSummary` (`colunas_nao_mapeadas`,
  `avisos`) em vez de erro — só uma linha sem nenhuma coluna reconhecível é
  descartada (`skipped_invalid`).

## `sinistros.py`

Prefixo `/sinistros`, tag `sinistros`. Rotas de leitura, consultando o banco
diretamente (sem passar por `services`, já que não há lógica de negócio além
de filtro/paginação).

### `GET /sinistros`

Listagem paginada, resposta `list[SinistroOut]`.

| Parâmetro | Tipo | Efeito |
|---|---|---|
| `tipo_registro` | `str \| None` | Filtro exato (`==`) por `Sinistro.tipo_registro` |
| `data_inicio` | `date \| None` | Filtro `Sinistro.data_sinistro >= data_inicio` |
| `data_fim` | `date \| None` | Filtro `Sinistro.data_sinistro <= data_fim` |
| `limit` | `int`, padrão `100`, máx. `1000` | Tamanho da página |
| `offset` | `int`, padrão `0`, mín. `0` | Deslocamento da página |

Resultado ordenado por `(data_sinistro, id_sinistro)` — ordenação
determinística, importante para paginação consistente entre chamadas
sucessivas.

### `GET /sinistros/{id}`

Detalhe de um sinistro pela PK interna `id` (não `id_sinistro`, que agora é
opcional e não é mais a chave primária — ver [`db.md`](./db.md)). `404`
(`"Sinistro não encontrado"`) se o `id` não existir.

## `mapa.py`

Sem prefixo, tag `mapa`. Expõe um único endpoint que devolve uma página HTML
completa (não JSON) com um mapa navegável.

### `GET /mapa`

Retorna `HTMLResponse` com uma página autocontida usando **Leaflet 1.9.4** +
**leaflet.heat 0.2.0** (carregados via CDN `unpkg.com`) e tiles do
**OpenStreetMap**.

> Este endpoint só funciona servido diretamente (fora de qualquer sandbox de
> artifacts, que bloqueia carregamento de tiles/scripts externos) — o
> navegador de quem acessa precisa ter acesso direto à internet para buscar
> os tiles do OSM e as libs do CDN.

#### Dados carregados do banco

```python
total = db.query(Sinistro).count()
rows = db.query(Sinistro).filter(
    Sinistro.latitude.is_not(None), Sinistro.longitude.is_not(None)
).all()
```

Só sinistros com coordenadas entram no mapa; `total` (todos) vs. `len(rows)`
(geocodificados) alimenta o contador `"{total_geo} de {total} sinistros com
coordenadas"` no painel — visibilidade direta de quanto da base ainda não
está geocodificada (ver pendência em [`arquitetura.md`](./arquitetura.md)).

Cada ponto serializado para o JS carrega: `lat`, `lon`, `data`
(`data_sinistro.isoformat()`), `turno`, `logradouro` (`.title()`-cased),
`tipo_registro`, `tipo_primario`, e as quatro contagens de gravidade
(`fatal`, `grave`, `leve`, `ileso`).

#### Contorno do município

```python
_DATA_DIR = Path(__file__).resolve().parents[4] / "data"
_BOUNDARY_PATH = _DATA_DIR / "municipio_ribeirao_preto.geojson"
_BOUNDARY_GEOJSON = json.loads(_BOUNDARY_PATH.read_text(encoding="utf-8"))
```

Carregado **uma vez**, no import do módulo (não a cada requisição) — o
arquivo é pequeno e estático, então não há motivo para reler/reparsear a
cada `GET /mapa`. Ver [`dados.md`](./dados.md) para a origem desse GeoJSON.

No front-end, é desenhado como `L.geoJSON` (camada `municipioLayer`, azul,
`color: '#1c5cab'`, `fillColor: '#2a78d6'`, `fillOpacity: 0.08`) e o mapa dá
`fitBounds` nele ao carregar — a área administrativa inteira do município
fica enquadrada de início, não só a região onde há sinistros geocodificados.
Um checkbox "Município (contorno)" liga/desliga essa camada.

#### Severidade e cores

```python
_SEVERITY_COLORS = {
    "fatal": "#d03b3b", "grave": "#ec835a", "leve": "#fab219",
    "ileso": "#0ca30c", "nao_informado": "#8a94a3",
}
```

No JS, `severidade(p)` deriva a severidade de um ponto pela **primeira**
contagem não-zero, nesta ordem de prioridade: `fatal > grave > leve > ileso`
— ou seja, um sinistro com 1 vítima grave e 2 ilesos é classificado como
`"grave"`. Usada para colorir o preenchimento dos marcadores individuais.

#### Peso de calor por gravidade

```python
_SEVERITY_WEIGHTS = {"fatal": 4, "grave": 2, "leve": 1, "ileso": 0.3}
_HEAT_FLOOR = 0.2
```

`pesoCalor(p)` (JS) soma `contagem_por_gravidade * peso` para as quatro
gravidades e aplica um piso (`Math.max(peso, _HEAT_FLOOR)`) para que
sinistros sem nenhuma gravidade informada não fiquem com peso zero e
desapareçam do calor. Esse peso é usado tanto na camada de calor quanto no
raio dos marcadores — sinistros mais graves aparecem mais "quentes" e
maiores, não apenas os mais numerosos.

#### Camada de calor (gradiente "semáforo de risco")

```js
const heatLayer = L.heatLayer(heatPoints, {
  radius: 34, blur: 26, max: 2.5, minOpacity: 0.25, maxZoom: 15,
  gradient: { 0.1: '#1a9850', 0.3: '#66bd63', 0.5: '#fee08b', 0.7: '#f46d43', 1.0: '#d73027' },
});
```

Paleta customizada (em vez do padrão azul→vermelho do `leaflet.heat`): verde
(`#1a9850`) nas áreas de calor baixo, passando por amarelo/laranja
(`#66bd63`, `#fee08b`, `#f46d43`) até vermelho (`#d73027`) nos pontos mais
expressivos. `minOpacity: 0.25` garante que mesmo áreas de calor baixo
fiquem minimamente visíveis sobre o mapa. Pontos de calor próximos somam
intensidade naturalmente via comportamento nativo do `leaflet.heat` — não há
lógica de "colisão" para a camada de calor em si (ao contrário dos
marcadores, abaixo). Um checkbox "Calor por gravidade" liga/desliga essa
camada; ela é adicionada ao mapa por padrão (`heatLayer.addTo(map)`).

#### Marcadores individuais com raio anti-sobreposição

```js
const MARCADOR_RAIO_MIN = 3;
const MARCADOR_RAIO_MAX = 9;
const MARCADOR_GAP_PX = 2;
```

Cada sinistro geocodificado vira um `L.circleMarker` (borda `#141414`,
preenchimento pela cor de severidade, popup com logradouro/data-turno/
tipo/gravidade). Ao contrário do calor, o raio dos marcadores **não** pode
crescer livremente com o peso de gravidade — em áreas densas isso faria
marcadores próximos se sobreporem visualmente. A função
`recalcularRaiosMarcadores()`:

1. Projeta a posição de todos os marcadores em pixels de tela
   (`map.latLngToContainerPoint`).
2. Para cada marcador, calcula a distância até o vizinho mais próximo.
3. Deriva um "raio desejado" a partir do peso de gravidade
   (`MARCADOR_RAIO_MIN + peso * 0.6`), mas o limita à metade da distância
   até o vizinho mais próximo menos uma margem (`MARCADOR_GAP_PX`), e a um
   teto absoluto (`MARCADOR_RAIO_MAX`).

Ou seja: o raio de um marcador só cresce até onde não invade a área do
vizinho mais próximo — o limite é a colisão espacial, não só a gravidade.
Recalculada em `zoomend` (`map.on('zoomend', recalcularRaiosMarcadores)`),
já que a distância em pixels entre dois pontos geográficos muda com o zoom.

**Estado atual:** a camada de marcadores (`markersLayer`) é construída e o
checkbox "Pontos individuais (detalhe)" existe no painel, mas o checkbox
nasce **desmarcado** e `markersLayer.addTo(map)` **não** é chamado na
inicialização — ou seja, por padrão só a camada de calor fica visível ao
carregar a página; os pontos individuais só aparecem se o usuário marcar a
opção manualmente.

#### Painel de controle

Três checkboxes (`toggle-municipio`, `toggle-heat`, `toggle-points`), cada
um ligando/desligando sua respectiva camada via `map.removeLayer`/
`layer.addTo(map)`. Abaixo deles, um contador de cobertura geográfica
(`{total_geo} de {total}`) e um texto de ajuda (`.hint`) explicando o
gradiente de calor e o comportamento de colisão dos raios.

#### Renderização do template

```python
html = _PAGE_TEMPLATE.format(
    pontos_json=..., cores_json=..., boundary_json=...,
    total_geo=..., total=...,
    peso_fatal=..., peso_grave=..., peso_leve=..., peso_ileso=..., piso_calor=...,
)
```

`_PAGE_TEMPLATE` é uma string Python com `str.format`; por isso todo `{` e
`}` literais do CSS/JS aparecem duplicados (`{{`/`}}`) no código-fonte —
necessário para escapar do mecanismo de template do `str.format`. Os dados
(pontos, cores, contorno do município) são injetados como JSON serializado
(`json.dumps(..., ensure_ascii=False)`) diretamente no `<script>`.

## `deps.py`

Dependências FastAPI compartilhadas entre rotas protegidas:

```python
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenData:
    token_data = decode_access_token(token)
    if token_data is None:
        raise HTTPException(status_code=401, ...)
    return token_data

def get_current_admin(token_data: TokenData = Depends(get_current_user)) -> str:
    if token_data.role != ROLE_ADMIN:
        raise HTTPException(status_code=403, ...)
    return token_data.username
```

`OAuth2PasswordBearer(tokenUrl="/auth/login")` faz duas coisas: extrai o
Bearer token do header `Authorization` (e devolve `401` sozinho se o header
estiver ausente/malformado, antes mesmo de `get_current_user` rodar), e
informa ao Swagger (`/docs`) onde fica o endpoint de login, para o botão
"Authorize" funcionar direto na UI interativa.

Duas camadas:
- **`get_current_user`**: exige só um token válido (qualquer papel).
  Nenhuma rota usa isso diretamente hoje, mas existe como base para
  `get_current_admin` e para futuras rotas que precisem só de "autenticado",
  sem exigir ser admin.
- **`get_current_admin`**: além de um token válido, exige `role="admin"`
  (`403 Forbidden` caso contrário). É o que protege `POST /ingest/csv`. Só o
  admin raiz emite tokens com esse papel (ver `POST /auth/login` acima);
  contas de `POST /auth/register` sempre têm `role="user"` e caem no `403`.

`decode_access_token`/`TokenData`/`ROLE_ADMIN` estão em
[`core/security.py`](./core.md#securitypy) e [`db/models.py`](./db.md).
