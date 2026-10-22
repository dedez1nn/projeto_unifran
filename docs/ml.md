# `src/ml/`: modelos de risco

Treino offline dos modelos de risco a partir da base **RENAEST** (Senatran)
de Ribeirão Preto. Roda por `scripts/treinar_risco.py`, publica o resultado
em tabelas do banco (`risco_*`, ver [`db.md`](./db.md)) e a API só lê essas
tabelas (`GET /risco/...`, ver [`api.md`](./api.md)). Nenhum módulo de
`app/` importa `ml/`, então pandas, scikit-learn e scipy ficam em
`requirements-ml.txt`, fora das dependências da API.

O núcleo de ocorrência é o `modelo_risco_acidentes_v3.py` do time de ML,
adaptado com três correções (ver [`ocorrencia.py`](#ocorrenciapy)).

## Como rodar

```bash
.venv/bin/pip install -r requirements-ml.txt   # já incluso em requirements-dev.txt
.venv/bin/python scripts/treinar_risco.py      # lê data/acidentes_ribeirao_preto.csv
```

Se existir `data/tipoveiculo_ribeirao_preto.csv` (tabela de veículos da
RENAEST, `--veiculos` para outro caminho), o treino também gera a previsão
por tipo de veículo do filtro do mapa; sem ela, o filtro não aparece. O
arquivo pode ser extraído do dump do time de dados:

```bash
pg_restore -a -t staging_tipoveiculo -f - bckbdacid.sql   # COPY em TSV; converter para CSV com ";"
```

Leva poucos segundos. Salva os CSVs e as métricas em `data/ml_saidas/`
(ignorado pelo git) e substitui o conteúdo das tabelas de risco do banco em
`DATABASE_URL`. `--sem-publicar` só treina e salva em disco; `--csv` aceita
também a tabela `acidentes_tratados` exportada do banco do time de dados.

Retreinar sempre que chegar uma extração nova da RENAEST: a previsão parte
do último mês da base.

## Por que esses recortes

O diagnóstico de qualidade (`dados.diagnostico_qualidade`, gravado em
`ml_execucoes.metricas.qualidade_por_ano`) explica cada decisão:

| Ano | Acidentes | Com coordenada | Com ferido registrado | Tipo de acidente informado |
|---|---|---|---|---|
| 2019-2021 | 3,5 a 4,2 mil | 0% | 56% a 94% | 47% a 78% |
| 2022 | 4,6 mil | 35% | 50% | 46% |
| 2023-2025 | 4,4 a 5,8 mil | 97% a 99% | 2% a 6% | 0% a 65% |
| 2026 (até abril) | 1,2 mil | 64% | 2% | 0% |

- **2018 fica de fora:** só traz os acidentes com óbito (início da série).
- **Mapa e vias só de 2023 em diante**, quando há coordenada.
- **Óbito é o único desfecho de gravidade**: a partir de 2023 o ferido não
  fatal praticamente deixa de ser registrado. Treinar gravidade com todos os
  anos faz o ano virar o preditor (2024+ seria "100% óbito").
- **Tipo de acidente não é usado**: some em 2025.
- **2025-11 não tem dados na fonte** e é tratado como mês não observado, não
  como "zero acidentes".

## Módulos

### `dados.py`

`carregar_acidentes(caminho)` aceita o CSV bruto da Senatran (`latin-1`,
`hora_acidente` em `HHMMSS`, `999999` = hora ausente) e a tabela
`acidentes_tratados` exportada, e devolve o mesmo DataFrame normalizado. Os
dois formatos foram conferidos registro a registro: hora, coordenadas,
óbitos e endereço batem em 100% dos 32.382 acidentes.

Ler `hora_acidente` direto como número dá `13900` para `"013900"`; era o
bug que fazia 99,9% dos acidentes caírem em "Noite" no notebook do Colab.
`normalizar_rua` unifica grafias ("AV. EDUARDO..." e "AVENIDA EDUARDO...").

### `ocorrencia.py`

Previsão de acidentes por célula de 0,005° (~550 m) para os próximos 12
meses, com backtest em 4 cortes (2024-10, 2024-12, 2025-02, 2025-04). Cada
corte treina só com alvos que terminam até ele.

- **Limpeza geográfica**: coordenadas fora do município, (0,0) ou
  "placeholder" (a mesma coordenada exata para 10+ endereços diferentes,
  típico de rodovia: 617 acidentes em 5 pontos) viram "sem coordenada".
- **Alocação fracionada** (`alocar`): o acidente sem coordenada, mas com
  rua, é distribuído entre as células onde aquela rua tem acidentes
  geocodificados. Recupera 558 acidentes.
- **Candidatos**: média histórica da célula (`BASE_taxa`), últimos 12 meses
  (`BASE_12m`), média suavizada pela vizinhança (`BASE_EB`, Gamma-Poisson),
  gradient boosting com perda de Poisson (`GBM`) e a média de `GBM` com
  `BASE_EB` (`MISTO_GBM_EB`). Vence o menor desvio de Poisson.
- **Nível**: top 5% das células = ALTO, próximos 15% = MÉDIO.
- **Vias** (`gerar_ranking`): cada célula reparte a previsão entre as ruas
  na proporção do histórico dela; a via soma as fatias. Entram as vias com
  15+ acidentes desde 2023 (205 vias).

Correções em relação à v3 do time de ML:

1. A alocação por rua usava o período inteiro, inclusive o futuro de cada
   corte do backtest. Agora cada corte usa só os acidentes até ele.
2. `escolher_modelo` podia eleger `BASE_taxa`, mas o ranking só aplicava
   `GBM`/`MISTO_GBM_EB` e caía em `BASE_EB` sem avisar. Agora backtest e
   ranking usam a mesma função (`prever`).
3. O ranking exporta a rua principal de cada célula e o agregado por via.

Também passou a contar a madrugada como "noite" (antes só `hora >= 18`).

**Resultado do backtest** (média dos 4 cortes):

| Modelo | Spearman | Captura top 5% | Desvio de Poisson | Previsto / real |
|---|---|---|---|---|
| `BASE_taxa` (escolhido) | 0,840 | 27,9% | **2,255** | 1,11 |
| `MISTO_GBM_EB` | 0,830 | 27,7% | 2,278 | 1,00 |
| `BASE_EB` | 0,832 | 27,3% | 2,321 | 1,08 |
| `GBM` | 0,818 | 27,4% | 2,588 | 0,91 |
| `BASE_12m` | 0,787 | 27,7% | 4,564 | 1,00 |

Com o vazamento da alocação corrigido, **a média histórica vence o gradient
boosting**: onde vai haver mais acidentes é, na prática, onde já houve. É uma
conclusão do estudo, não uma falha; o site a mostra na seção de metodologia.

Diagnósticos que não viram recurso no site:

- `avaliar_indice_obitos`: para capturar óbitos futuros, ordenar as células
  pelo histórico de acidentes (36% nas top 100) funciona melhor que pelos
  acidentes previstos (29%) ou pelos óbitos históricos (24%). Óbito por
  célula é raro demais para ser previsto diretamente.
- `avaliar_gravidade_por_horario`: P(óbito | acidente) só com hora/dia/mês
  tem AUC 0,60. O que explica gravidade (tipo de colisão, veículos) só se
  conhece depois do acidente.

### `veiculos.py`

Previsão por tipo de veículo envolvido (moto, carro, caminhão, ônibus),
para o filtro "Veículo" do mapa. Para cada célula, a fração dos acidentes
que envolvem a categoria entre os acidentes com tipo informado, suavizada
em direção à fração da cidade (peso de 20 acidentes), vezes a previsão da
célula. O nível é recalculado entre as células para cada categoria.

| Categoria | Tipos da RENAEST | Presente em (cidade, desde 2023) |
|---|---|---|
| Carro | automóvel, caminhonete, camioneta, utilitário | 79% dos acidentes |
| Moto | motocicleta, motoneta, ciclomotor, triciclo | 55% |
| Caminhão | caminhão, caminhão-trator, semirreboque, reboque | 5% |
| Ônibus | ônibus, micro-ônibus | 4% |

As frações somam mais de 100% porque um acidente pode envolver mais de uma
categoria (moto x carro). Bicicleta fica de fora: são só 57 registros na
base inteira. Limitação: o tipo de veículo é informado em 50% dos acidentes
desde 2023 (55% em 2023, 61% em 2024, cerca de um terço em 2025-26), e a
previsão supõe que os acidentes sem tipo têm a mesma composição; o site
mostra esse aviso junto do filtro.

### `tendencia.py`

Zonas em alta: células com mais acidentes nos últimos 6 meses do que a
fatia histórica delas no total da cidade faria esperar (teste de Poisson,
p < 0,01, razão >= 1,5 e 6+ acidentes recentes). Comparar fatias, e não
contagens, neutraliza o que muda para a cidade inteira ao mesmo tempo: o
mês sem dados e a queda de cobertura de coordenadas em 2026. Hoje: 5 zonas.

### `pontos_criticos.py`

Aglomerados de acidentes com óbito (DBSCAN com distância haversine, raio de
150 m, mínimo de 3 acidentes fatais), sem os placeholders. Não há rótulo de
treino nem previsão, só a localização do que já aconteceu. Hoje: 5 pontos,
o mais letal na SP-322 (4 acidentes, 8 óbitos).

### `perfil.py`

Fração dos acidentes de cada via em cada dia da semana x hora (168
combinações), suavizada em direção ao perfil da cidade (peso de 50
acidentes). Usa 2019+, porque hora e logradouro existem desde o início.
`quantis_taxa_hora` publica a distribuição de "acidentes por ano numa hora
da semana" entre todas as vias x horas, usada pela API no índice da
simulação.

### `serie_mensal.py`

Total mensal da cidade para os próximos 12 meses: regressão de Poisson com
sazonalidade por mês, ajustada de 2021 em diante, sem tendência, com
intervalo de 95% de quase-Poisson. Backtest em 5 cortes de 12 meses:

| Método | Erro médio por mês (MAPE) |
|---|---|
| Sazonalidade desde 2021 (escolhido) | **15,1%** |
| Mesmo com tendência log-linear | 22,7% |
| Repetir o mesmo mês do ano anterior | 22,8% |
| Média dos últimos 12 meses | 22,4% |

A tendência piorava porque extrapolava o salto de 2023. Atenção: os meses
de 2026 vêm abaixo do nível histórico (cerca de 300 por mês, contra 380 a
400 em 2024-2025), o que pode ser atraso de registro na fonte. Se for queda
real, a previsão tende a ficar acima do que acontecer.

### `treino.py` e `publicar.py`

`treinar(csv)` encadeia os módulos acima e devolve um `ResultadoTreino`;
`publicar` grava tudo numa única transação (quem consulta a API vê a versão
anterior completa ou a nova completa) e registra a execução em
`ml_execucoes`, com as métricas e o resumo da limpeza.

## Limitações conhecidas

- A previsão por célula não tem dimensão de hora; o risco por horário vem
  do perfil histórico da via (`perfil.py`), não de um modelo.
- O clima não entra em nada: a base registra o clima de cada acidente, mas
  não por quanto tempo choveu, então não há como medir o efeito da chuva.
- Vias de 2019-2022 não têm coordenada: o mapa reflete só 2023+.
- Os 4 cortes do backtest se sobrepõem (janelas de 12 meses espaçadas de 2),
  então a média deles é mais estável do que seria com janelas independentes.
