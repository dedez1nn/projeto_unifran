# Dados

Arquivos de dados usados/gerados pelo projeto — não são código, mas fazem
parte do comportamento observável da aplicação.

## `sinistros_12-2025.csv`

Dataset bruto oficial, versionado na raiz do repositório. 16.817 linhas
(16.816 linhas de dados + cabeçalho), cobrindo sinistros de trânsito de
**todo o estado de São Paulo** — o filtro para Ribeirão Preto-SP é aplicado
na ingestão (`MUNICIPIO_ALVO`), não no dado bruto. Do total, 447 linhas são
de Ribeirão Preto (`tests/test_adapters.py` fixa essas contagens como
asserção — ver [`tests.md`](./tests.md)).

Formato:
- Encoding **latin-1** (ISO-8859-1).
- Delimitador `;`.
- Decimais em vírgula (padrão brasileiro).
- Datas `dd/mm/aaaa`, horas `HH:MM`.
- Flags booleanas como `"S"`/vazio.

Ver [`services.md`](./services.md#adapterspy) para o mapeamento por alias
que lida com essas particularidades (entre outros formatos).

É também a fonte padrão usada por
[`scripts/seed_from_csv.py`](./scripts.md) quando nenhum caminho é passado
como argumento.

## `acidentes_ribeirao_preto.csv`

Fonte alternativa, formato **diferente** do INFOSIGA oficial (colunas como
`num_acidente`, `data_acidente` em `aaaa-mm-dd`, `codigo_ibge`, sem colunas
separadas de gravidade grave/leve/ileso — só `qtde_obitos` e
`qtde_feridosilesos` combinado). Não versionado (arquivo local, grande);
ingerido pelo mesmo `scripts/seed_from_csv.py`/`POST /ingest/csv` graças ao
mapeamento por alias em `services/adapters.py` — colunas sem alias
conhecido (ex.: `cond_meteorologica`, `tp_pavimento`) ficam em
`raw_data` e aparecem em `colunas_nao_mapeadas` no resumo da ingestão, ver
[`services.md`](./services.md).

## Banco de dados

O banco padrão é **Postgres** (imagem `postgis/postgis`), subido via
`docker-compose.yml` na raiz do projeto — ver [`configuracao.md`](./configuracao.md).
Os dados persistem no volume Docker `postgres_data`, fora do controle de
versão.

Contém uma única tabela, `sinistros`, mapeada pelo model ORM `Sinistro` —
ver [`db.md`](./db.md).

`sinistros.db` (SQLite) só aparece se `DATABASE_URL` for explicitamente
sobrescrita para um arquivo local — é o que `tests/conftest.py` faz, para
manter a suíte de testes rápida e isolada do Postgres (ver
[`tests.md`](./tests.md)). Está no `.gitignore` via `*.db`.

## `data/municipio_ribeirao_preto.geojson`

Contorno da malha municipal do **IBGE** para Ribeirão Preto-SP (código de
área `3543402`). Um `FeatureCollection` com uma única `Feature` do tipo
`Polygon`, com 84 pares de coordenadas `[longitude, latitude]` (formato
GeoJSON padrão — ordem invertida em relação ao `latitude, longitude` usado
no resto do projeto, ex. `Sinistro.latitude`/`Sinistro.longitude` e o centro
do mapa em `mapa.py`).

Arquivo pequeno (4 KB), de conteúdo estático — não é gerado nem atualizado
por nenhum script do projeto; foi adicionado manualmente ao repositório.
Usado exclusivamente por [`api.md`](./api.md#mapapy) para desenhar o
contorno azul do município e enquadrar o mapa (`fitBounds`) na área
administrativa inteira, cobrindo além dos pontos onde há sinistros
geocodificados.

## `data/dados_infosiga.zip`

Histórico completo do InfoSiga para o estado de SP (2015 a jul/2026):
`sinistros_*` (1,42 milhão de linhas, 645 municípios), `pessoas_*` e
`veiculos_*`. Fora do git pelo tamanho (132 MB compactado, 935 MB
descompactado); carregado por `scripts/carregar_infosiga.py`. Para Ribeirão
Preto são 33.389 sinistros e 47.631 pessoas; de 2015 a 2018 só há os
sinistros com óbito (no estado inteiro), e a cobertura de coordenadas cai
para 41% em 2025.

## `data/populacao_municipios_sp.csv`

População dos 645 municípios de SP de 2014 a 2026, da API do IBGE:
estimativas anuais (agregado 6579) e Censo 2022 (agregado 4709); 2023, que
o IBGE não estimou, é a média entre o Censo 2022 e a estimativa de 2024.
Versionado no git (pequeno e público), usado nos indicadores por 100 mil
habitantes.

## `data/tipoveiculo_ribeirao_preto.csv`

Tabela de veículos da RENAEST (Ribeirão Preto), extraída do dump do time de
dados (`staging_tipoveiculo`). Fora do git; alimenta o filtro por veículo
dos modelos de risco (ver [`ml.md`](./ml.md)).
