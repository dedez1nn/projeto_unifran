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

## O que continua sendo simulação (e por quê)

- **Simulação de risco** (`predicao.html`): o backend ainda não tem um
  modelo de predição nem endpoint para isso — o projeto, até aqui, só
  ingere e visualiza os dados oficiais. `RiscoIA.calculateFallback` é uma
  heurística demonstrativa, deixada explícita na interface, para ilustrar
  como a tela se comportaria quando o modelo existir.
- **Zonas de risco no mapa** (`zoneData` em `script.js`): mesma razão acima
  — são 5 zonas com risco "chumbado" no código, não vêm de nenhuma análise
  real. Ficam como camada separada da camada de sinistros reais.
- **Recuperação de senha** (`forgot-password.html`): o backend não tem
  endpoint de redefinição de senha (exigiria um serviço de e-mail, fora do
  escopo atual). A tela avisa isso e orienta a procurar o administrador, em
  vez de simular uma troca de senha que não teria efeito nenhum na conta
  real.
- **Tema claro/escuro**: não implementado - o layout é escuro por padrão e
  `style.css` (~1900 linhas) não usa variáveis CSS (`:root`); extrair as
  cores para viabilizar um toggle é um refactor maior, fora do escopo desta
  rodada de integração.
