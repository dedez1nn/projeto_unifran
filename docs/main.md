# `src/app/main.py`

Ponto de entrada da aplicação FastAPI.

```python
from app.api.routes import health, ingestion, mapa, sinistros
from app.db.models import Sinistro  # noqa: F401 - garante registro do model no Base
from app.db.session import Base, engine

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="API de Sinistros de Trânsito - Ribeirão Preto",
    description="...",
    version="0.1.0",
)

app.include_router(health.router)
app.include_router(ingestion.router)
app.include_router(mapa.router)
app.include_router(sinistros.router)
```

### O que faz, em ordem

1. **Importa `Sinistro`** só pelo efeito colateral do `import` (comentário
   `# noqa: F401` avisa o linter disso de propósito): o SQLAlchemy só sabe
   criar a tabela de um model se a classe tiver sido registrada em
   `Base.metadata`, o que acontece na definição da classe. Sem esse import,
   `Base.metadata.create_all` não teria nada para criar.
2. **`Base.metadata.create_all(bind=engine)`** — cria as tabelas que ainda
   não existem no banco (idempotente: não recria as que já existem). É a
   única forma de "migração" de schema no projeto hoje — ver
   [`db.md`](./db.md).
3. **Instancia o `FastAPI`** com metadados usados na doc automática
   (Swagger em `/docs`, ReDoc em `/redoc`).
4. **Registra o `CORSMiddleware`** com as origens de `settings.cors_origins`
   (env var `CORS_ORIGINS`, ver [`core.md`](./core.md)) — sem isso, nenhum
   browser em outra origem conseguiria consumir a API.
5. **Registra os routers**, cada um definindo seu próprio prefixo/tags —
   ver [`api.md`](./api.md) para o que cada um expõe.
6. **Monta `frontend/` como arquivos estáticos em `/`** (`StaticFiles(...,
   html=True)`), por último — os routers acima são checados primeiro, então
   uma rota como `/auth/login` nunca cai no mount; ele só serve o que
   sobra (`index.html`, `login.html`, `style.css`, `script.js` etc.). Como o
   frontend passa a ser servido pela própria API, chamadas do JS para
   `RiscoIA.apiUrl(...)` (ver `frontend/utils.js`) usam caminho relativo —
   mesma origem, sem depender de CORS. Se o diretório `frontend/` não
   existir (ex.: checkout parcial), o mount é pulado e a API funciona normal,
   só sem servir HTML.

### Rodando

```bash
uvicorn app.main:app --app-dir src --reload
```

O `--app-dir src` é necessário porque os módulos são importados como
`app.xxx` (não `src.app.xxx`) — o pacote raiz é `app`, dentro de `src/`.
