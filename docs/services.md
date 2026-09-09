# `src/app/services/`

Lógica de negócio: mapeamento genérico de CSV e ingestão no banco. Isolada da
camada `api` para que as rotas fiquem finas (validação HTTP + delegação) e
essa lógica seja testável sem precisar subir a aplicação — ver
`tests/test_adapters.py` em [`tests.md`](./tests.md).

## `adapters.py`

Mapeamento **por alias de coluna**, não por um schema fixo: não existe um
único formato de CSV obrigatório. `_FIELD_MAP` associa cada campo do model
`Sinistro` a uma lista de nomes de coluna aceitos (normalizados — sem
acento, minúsculo) e a uma função de conversão. Isso permite que fontes bem
diferentes — o CSV oficial INFOSIGA (`id_sinistro`, `data_sinistro`,
`municipio`...) e outras extrações (ex.: `num_acidente`, `data_acidente`,
`codigo_ibge`...) — sejam ingeridas pelo mesmo caminho de código, sem um
parser dedicado por formato.

### Conversores de campo

| Função | Entrada → saída | Detalhe |
|---|---|---|
| `_to_int(value)` | `"1.0"` → `1` | Passa por `float()` antes de `int()` |
| `_to_float(value)` | `"-20,0393654"` → `-20.0393654` | Troca vírgula por ponto (decimal brasileiro) |
| `_to_bool_flag(value)` | `"S"`/`"SIM"`/`"TRUE"`/`"1"`/`"YES"` → `True`, qualquer outra coisa → `False` | Cobre as variações mais comuns de flag booleana em CSVs de fontes diferentes |
| `_to_date(value)` | `"01/12/2025"` ou `"2025-12-01"` → `date(2025, 12, 1)` | Tenta `%d/%m/%Y` e `%Y-%m-%d`, nessa ordem; nenhum dos dois → `ValueError` |
| `_to_time(value)` | `"12:46"`/`"12:46:00"`/`"124600"` → `time(12, 46)` | Tenta os três formatos, nessa ordem |

Todas tratam string vazia/`None` retornando `None` (exceto `_to_bool_flag`).
Uma falha de conversão (`ValueError`) **não derruba a linha**: vira um aviso
(`ParsedRow.warnings`) e o campo fica `None` — ver abaixo.

### `parse_row_generico(raw: dict[str, str]) -> ParsedRow`

```python
@dataclass
class ParsedRow:
    fields: dict[str, Any]
    source_row_id: str
    unmapped_columns: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    municipio_informado: bool = False
```

1. Normaliza os nomes de coluna do CSV (`_norm`: remove acento, minúsculo,
   espaço → `_`) e tenta casar cada um contra os aliases de `_FIELD_MAP`.
2. Colunas do CSV que não batem com nenhum alias conhecido viram
   `unmapped_columns` (mas continuam preservadas em `raw_data` pelo
   `ingestion_service`, ver abaixo — nada se perde).
3. **Chave natural da linha** (`source_row_id`): se um `id_sinistro`
   reconhecível foi mapeado, ele vira a chave (como `str`). Senão, é usado o
   SHA-1 do conteúdo bruto da linha inteira — mesma linha ingerida de novo
   produz a mesma chave (idempotente), mas qualquer edição no arquivo-fonte
   gera uma linha *nova* em vez de atualizar a existente (não há como saber
   que é "a mesma linha, editada" sem um id explícito). Um aviso é adicionado
   nesse caso.
4. Levanta `LinhaInvalidaError` só se **nenhuma** coluna bateu com nenhum
   alias — ou seja, o pior caso é uma linha completamente ilegível, não um
   campo individual malformado.
5. `municipio_informado` indica se o CSV declara alguma coluna de município
   reconhecida (mesmo que vazia numa linha específica) — usado pelo
   `ingestion_service` para decidir se o filtro de `MUNICIPIO_ALVO` se
   aplica a este arquivo.

## `ingestion_service.py`

### `ingest_csv_bytes(db, file_bytes, source_filename) -> IngestionSummary`

Orquestra a ingestão completa de um CSV de formato arbitrário:

1. **Decodifica** tentando `utf-8-sig` → `utf-8` → `latin-1` (o último
   sempre funciona, nunca levanta `UnicodeDecodeError`) — não assume mais um
   encoding fixo, já que fontes diferentes usam encodings diferentes.
2. **Detecta o delimitador** com `csv.Sniffer` (`;`, `,` ou tab), com `;`
   como fallback se a detecção falhar.
3. **Deriva `source_name` do nome do arquivo** (`_source_name_from_filename`:
   normaliza acento/caixa, troca não-alfanumérico por `_`, corta em 50
   chars) — cada arquivo é seu próprio namespace de `source_row_id`. Isso é
   deliberado: sem isso, um `id_sinistro` do CSV oficial que coincidisse por
   acaso com um `num_acidente` de outro arquivo seria tratado como "a mesma
   linha" e um sinistro sobrescreveria os dados de outro completamente
   diferente (bug real, encontrado e corrigido — ver histórico do commit).
4. **Pré-carrega** todos os registros já existentes desse `source_name` numa
   consulta só (`dict[source_row_id, Sinistro]`) — não uma consulta por
   linha. Isso resolve dois problemas de uma vez: performance (evita N+1
   queries; um arquivo de 30 mil linhas fazia 30 mil idas ao banco antes
   dessa mudança) e uma linha duplicada *dentro do mesmo arquivo* (mesmo
   `source_row_id` duas vezes) — sem o dict em memória, a segunda ocorrência
   não via a primeira (ainda não commitada, `autoflush=False` em
   `db/session.py`) e o `commit()` final quebrava com `IntegrityError` na
   constraint única, perdendo a ingestão do arquivo inteiro.
5. Para cada linha, chama `parse_row_generico`. Se levantar
   `LinhaInvalidaError`, conta em `skipped_invalid` e registra um aviso
   (`"linha N: ..."`).
6. Acumula `unmapped_columns` de todas as linhas em `colunas_nao_mapeadas`
   (deduplicado, no resumo final) e os avisos de cada linha, prefixados com o
   número da linha — até `AVISOS_MAX` (50) avisos; o excedente vira uma
   última linha `"... e mais N aviso(s) omitido(s)"` em vez de crescer sem
   limite.
7. Se `municipio_informado`, filtra por `settings.municipio_alvo`
   (`skipped_other_municipio`); se **nenhuma** linha do arquivo declarou
   município, o filtro não é aplicado a nenhuma linha e um aviso avisa disso
   explicitamente (assume que o arquivo já veio pré-filtrado para o
   município certo — não há como verificar sem a coluna).
8. Preenche `source_name`, `source_row_id` (vindo do `ParsedRow`),
   `source_file`, `ingested_at`, e `raw_data` (a linha crua inteira, chaves
   convertidas para `str`) no dict a persistir.
9. **Upsert por `(source_name, source_row_id)`** — não mais por
   `id_sinistro` (ver [`db.md`](./db.md) para o porquê): busca no dict
   pré-carregado (atualizado a cada `insert` desta mesma execução também);
   se existir, atualiza (`setattr` em loop) e conta em `updated`; senão, cria
   um `Sinistro(**data)` novo, adiciona ao dict e conta em `inserted`.
10. Ao final do loop, `db.commit()` — um único commit para o arquivo inteiro
    (atômico: ou tudo é persistido, ou nada).
11. Retorna `IngestionSummary` com as contagens, `colunas_nao_mapeadas`
    (ordenadas) e `avisos` (linha a linha, com números de linha) — dá
    visibilidade completa do que deu certo, o que faltou mapear e o que
    falhou, sem esconder nada atrás de uma contagem agregada.

Essa função é o único ponto de entrada de dados no banco, usada tanto por
`api/routes/ingestion.py` (via HTTP) quanto por `scripts/seed_from_csv.py`
(via linha de comando, aceitando múltiplos arquivos numa chamada só) — ver
[`api.md`](./api.md) e [`scripts.md`](./scripts.md).

**Idempotência:** como o upsert é feito por `(source_name, source_row_id)`,
rodar `ingest_csv_bytes` duas vezes com o mesmo arquivo produz o mesmo
estado final do banco (a segunda vez, tudo cai em `updated`) — inclusive
para arquivos sem `id_sinistro` reconhecível, graças ao hash de conteúdo
como chave natural.
