# `scripts/`

## `seed_from_csv.py`

Popula a base local a partir de **um ou mais** CSVs de sinistros — qualquer
schema reconhecível pelo mapeamento por-alias de `app/services/adapters.py`,
não só o formato oficial — **sem** precisar subir o servidor HTTP nem token
de admin. É o caminho recomendado para ingerir vários arquivos de fontes
diferentes numa base nova (ex.: num computador novo, ver
[`configuracao.md`](./configuracao.md) para o setup completo).

```bash
python scripts/seed_from_csv.py [arquivo1.csv arquivo2.csv ...]
# sem argumentos: usa dados/sinistros_12-2025.csv
```

### Como funciona

```python
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.db.session import Base, SessionLocal, engine
from app.services.ingestion_service import ingest_csv_bytes

def main(csv_paths: list[Path]) -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for csv_path in csv_paths:
            content = csv_path.read_bytes()
            summary = ingest_csv_bytes(db, content, csv_path.name)
            print(f"=== {csv_path.name} ===")
            print(summary.model_dump_json(indent=2))
    finally:
        db.close()
```

- Insere `src/` no `sys.path` manualmente (o script roda fora do pacote
  `app`, então precisa desse ajuste para conseguir `import app...`) — o
  mesmo padrão usado em [`tests/conftest.py`](./tests.md).
- Cria as tabelas (`Base.metadata.create_all`) — idempotente, então rodar o
  script contra um banco já existente não recria nada.
- Itera sobre todos os caminhos recebidos, ingerindo um de cada vez (mesma
  sessão de banco), e delega cada arquivo inteiramente para
  `ingest_csv_bytes` — o mesmo caminho de código usado pelo endpoint
  `POST /ingest/csv` (ver [`services.md`](./services.md) e
  [`api.md`](./api.md)). Ou seja, popular o banco via script ou via upload
  HTTP tem exatamente o mesmo comportamento (mesma detecção de
  formato/encoding, mesmo upsert idempotente).
- Imprime o `IngestionSummary` de cada arquivo como JSON formatado
  (`indent=2`) no stdout, sob um cabeçalho `=== nome_do_arquivo.csv ===` —
  dá visibilidade imediata do que foi inserido/atualizado/pulado, quais
  colunas não foram reconhecidas e quais avisos apareceram, arquivo por
  arquivo, sem precisar consultar a API depois.

### Quando usar

- **Bootstrap num computador novo:** clonar o repo, subir o banco
  (`docker compose up -d db` ou apontar `DATABASE_URL` para outro lugar,
  inclusive SQLite) e rodar este script com os CSVs disponíveis — não
  precisa da API rodando nem de login de admin.
- **Alimentar de várias fontes:** como o mapeamento é por alias de coluna
  (não um schema fixo), arquivos de formatos diferentes podem ser passados
  na mesma chamada; cada um recebe seu próprio `IngestionSummary`, então dá
  pra ver exatamente o que cada fonte contribuiu (e o que não foi
  reconhecido nela) sem misturar os números.
- **Reingestão manual em dev:** mais rápido que montar um upload
  `multipart/form-data` manualmente para testar o pipeline de ingestão.

## `hash_password.py`

Gera o hash bcrypt de uma senha para colocar em `ADMIN_PASSWORD_HASH`
(`.env`) — ver [`core.md`](./core.md#securitypy).

```bash
python scripts/hash_password.py
# Senha do admin: <digitada, sem eco>
# Confirme a senha: <digitada, sem eco>
# <hash bcrypt impresso no stdout>
```

Usa `getpass.getpass` (não `input()`) para a senha não ecoar no terminal
nem ficar no histórico do shell, e pede confirmação duas vezes antes de
gerar o hash (`bcrypt.gensalt()` + `bcrypt.hashpw`) — evita configurar
`ADMIN_PASSWORD_HASH` com uma senha digitada errada por engano. Roda uma
única vez, manualmente, ao configurar o ambiente; não é chamado por nenhum
outro script/rota.

## `treinar_risco.py`

Treina os modelos de risco e publica o resultado no banco da API.

```bash
.venv/bin/python scripts/treinar_risco.py [--csv data/acidentes_ribeirao_preto.csv]
                                          [--veiculos data/tipoveiculo_ribeirao_preto.csv]
                                          [--saida data/ml_saidas] [--sem-publicar]
```

Precisa de `requirements-ml.txt`. Lê a base RENAEST (CSV bruto da Senatran
ou a tabela `acidentes_tratados` exportada), roda o pipeline de `src/ml/`,
salva CSVs e métricas em `--saida` e substitui as tabelas `risco_*` do banco
em `DATABASE_URL`. `--veiculos` (opcional; usa o arquivo padrão se ele
existir) gera a previsão por tipo de veículo do filtro do mapa. Detalhes do método e dos resultados em [`ml.md`](./ml.md).
