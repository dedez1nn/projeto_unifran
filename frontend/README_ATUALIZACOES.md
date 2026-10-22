# RiscoIA (frontend) - integração com o backend real

Este frontend (HTML/CSS/JS puro, sem build) começou como um protótipo
separado, com login/cadastro/histórico simulados inteiramente no navegador
(`localStorage`/`sessionStorage`). Esta versão substitui essa simulação pela
integração com a API real do projeto (`src/app/`, ver [`docs/api.md`](../docs/api.md)).

## O que passou a vir do backend

- **Login/cadastro/sessão**: `POST /auth/login`, `POST /auth/register` e
  `GET /auth/me` (ver `utils.js`/`script.js`). O token é um JWT de verdade
  emitido pelo backend; a sessão expira de acordo com o `exp` do próprio
  token (`ACCESS_TOKEN_EXPIRE_MINUTES`), não mais um prazo fixo inventado no
  frontend. Hash de senha (bcrypt) é feito no backend — o frontend não
  guarda mais senha nem hash em lugar nenhum.
- **Mapa e gráficos do dashboard**: `GET /sinistros/geojson` alimenta uma
  camada real de sinistros no mapa (`index.html`), e os gráficos "Sinistros
  por período"/"Vias com maior incidência" passaram a refletir essa mesma
  consulta em vez de números fixos.
- **Importação de CSV**: painel visível só para o admin (`role: "admin"`),
  que chama `POST /ingest/csv`.
- **Status do backend**: o indicador da tela de login consulta `GET /health`.

## Modelos de risco (`GET /risco/...`)

Com um modelo publicado (`scripts/treinar_risco.py`, ver
[`docs/ml.md`](../docs/ml.md)), estas partes deixam de ser demonstrativas:

- **Mapa**: as zonas são as células com previsão de 12 meses, filtráveis por
  nível, por "em alta" e por tipo de veículo envolvido (`GET /risco/zonas`,
  `GET /risco/veiculos`), no lugar das 5 zonas fixas. Os filtros antigos de
  horário e clima saíram: a previsão por zona é anual (o horário fica na
  simulação) e o efeito do clima não é mensurável na base.
- **Áreas que merecem atenção**: pontos críticos de acidentes com óbito
  (`GET /risco/pontos-criticos`), completados com zonas em alta.
- **Simulação de risco**: o seletor lista as vias reais (`GET /risco/vias`)
  e o resultado vem de `GET /risco/simular`, com índice 0-100 e os fatores.
- **Risco agora** (monitoramento): `GET /risco/agora` com o dia e a hora do
  relógio. O clima ao vivo é exibido, mas não entra no cálculo.
- **Zonas em alta** (monitoramento), **previsão mensal** (gráficos) e o
  cartão **Modelo publicado** (metodologia), que mostra também quando a
  média histórica venceu o ML no backtest.

Sem modelo publicado (ou com a API fora do ar), cada parte volta ao
comportamento anterior, sinalizado como demonstrativo.

## Páginas de dados (`GET /analise/...`)

O site deixou de mandar para o portal do InfoSiga para consultar dados.
Quatro páginas novas, todas em `analise.js`:

- **Explorar dados** (`explorar.html`): filtros cruzados (período, gravidade,
  tipo, turno, tipo de via, via) que atualizam indicadores, série mensal,
  tipos, veículos, hora, dia da semana, matriz dia x hora, mapa de calor,
  ranking de vias, perfil das vítimas e exportação em CSV.
- **Ficha** (`ficha.html?via=...` ou `?celula=...`): tudo isso para uma via
  ou zona, mais a previsão de risco dela. Abre a partir do ranking de vias,
  do popup das zonas no mapa e dos cartões de pontos críticos.
- **Comparar cidades** (`comparar.html`): ranking por 100 mil habitantes das
  cidades de SP de porte parecido, evolução anual e tabela completa.
- **Dados** (`dados.html`): fontes, limitações calculadas a partir dos
  números e o preenchimento de cada campo por ano, no InfoSiga e na RENAEST.

No dashboard, a camada de sinistros reais e os gráficos do topo passaram a
mostrar os últimos 12 meses da base (antes eram os 1.500 registros mais
antigos).

## O que continua sendo simulação (e por quê)

- **Simulação e zonas sem modelo publicado**: `RiscoIA.calculateFallback` e
  as 5 zonas de `zoneData` (`script.js`) continuam como reserva, usadas só
  quando `GET /risco/...` não tem modelo ou está fora do ar.
- **Recuperação de senha** (`forgot-password.html`): o backend não tem
  endpoint de redefinição de senha (exigiria um serviço de e-mail, fora do
  escopo atual). A tela avisa isso e orienta a procurar o administrador, em
  vez de simular uma troca de senha que não teria efeito nenhum na conta
  real.
- **Tema claro/escuro**: não implementado - o layout é escuro por padrão e
  `style.css` (~1900 linhas) não usa variáveis CSS (`:root`); extrair as
  cores para viabilizar um toggle é um refactor maior, fora do escopo desta
  rodada de integração.
