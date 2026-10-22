"use strict";

/*
 * RiscoIA - script.js
 * -------------------------------------------------------------------------
 * Autenticação, mapa e predição integrados com o backend real (FastAPI, ver
 * `src/app/main.py`). Funções utilitárias compartilhadas (normalize,
 * showMessage, sessão etc.) moram em utils.js e são usadas via o objeto
 * global `RiscoIA`.
 */

// ---------------------------------------------------------------------
// Status do backend (GET /health) - só existe o elemento em login.html.
// ---------------------------------------------------------------------
(async () => {
    const dot = document.getElementById("backendStatusDot");
    const text = document.getElementById("backendStatusText");
    if (!dot || !text) return;

    try {
        const response = await fetch(RiscoIA.apiUrl("/health"));
        if (!response.ok) throw new Error("offline");
        text.textContent = "Sistema de análise online";
    } catch (error) {
        dot.classList.add("offline");
        text.textContent = "Backend indisponível no momento";
    }
})();

// ---------------------------------------------------------------------
// Autenticação
// ---------------------------------------------------------------------
const loginForm = document.getElementById("loginForm");
const registerForm = document.getElementById("registerForm");
const switchAuth = document.getElementById("switchAuth");

// Autentica direto contra `POST /auth/login` (form-urlencoded, é o que
// `OAuth2PasswordRequestForm` do backend espera) e, com o token em mãos,
// busca a identidade (nome/papel) em `GET /auth/me` para montar a sessão.
// Usada tanto pelo login quanto logo após um cadastro bem-sucedido.
async function authenticate(identity, password) {
    const loginResponse = await fetch(RiscoIA.apiUrl("/auth/login"), {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ username: identity, password })
    });
    if (!loginResponse.ok) {
        const erro = await loginResponse.json().catch(() => null);
        throw new Error(erro?.detail || "Usuário/e-mail ou senha incorretos.");
    }
    const { access_token: token } = await loginResponse.json();

    const meResponse = await fetch(RiscoIA.apiUrl("/auth/me"), {
        headers: { Authorization: "Bearer " + token }
    });
    const user = meResponse.ok ? await meResponse.json() : { username: identity, role: "user", name: null, email: null };

    RiscoIA.startSession(token, user);
}

if (loginForm) {
    const loginButton = document.getElementById("loginButton");
    const loginButtonText = document.getElementById("loginButtonText");
    const loginLoading = document.getElementById("loginLoading");

    // Se a pessoa caiu aqui porque a sessão expirou (ver checagem periódica
    // de RiscoIA.isSessionValid mais abaixo), avisa o motivo em vez de só
    // devolver para a tela de login sem explicação.
    if (new URLSearchParams(location.search).get("expired") === "1") {
        RiscoIA.showMessage(document.getElementById("loginMessage"), "Sua sessão expirou. Faça login novamente.", "error");
    }

    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const identity = RiscoIA.normalize(document.getElementById("loginUsername")?.value);
        const password = document.getElementById("loginPassword")?.value || "";
        const msg = document.getElementById("loginMessage");

        if (!identity || !password) {
            RiscoIA.showMessage(msg, "Preencha e-mail/usuário e senha.", "error");
            return;
        }

        loginButton && (loginButton.disabled = true);
        loginButtonText?.classList.add("hidden");
        loginLoading?.classList.remove("hidden");

        try {
            await authenticate(identity, password);
            window.location.href = "index.html";
        } catch (error) {
            loginButton && (loginButton.disabled = false);
            loginButtonText?.classList.remove("hidden");
            loginLoading?.classList.add("hidden");
            RiscoIA.showMessage(msg, error.message || "Não foi possível entrar. Tente novamente.", "error");
        }
    });
}

if (registerForm) {
    registerForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const name = document.getElementById("registerName")?.value.trim();
        const email = RiscoIA.normalize(document.getElementById("registerEmail")?.value);
        const username = RiscoIA.normalize(document.getElementById("registerUsername")?.value);
        const password = document.getElementById("registerPassword")?.value || "";
        const confirm = document.getElementById("registerPasswordConfirm")?.value || "";
        const msg = document.getElementById("registerMessage");

        if (!name || name.length < 3) {
            return RiscoIA.showMessage(msg, "Digite seu nome completo.", "error");
        }
        if (!RiscoIA.isValidEmail(email)) {
            return RiscoIA.showMessage(msg, "Digite um e-mail válido.", "error");
        }
        if (username.length < 3) {
            return RiscoIA.showMessage(msg, "O usuário precisa ter pelo menos 3 caracteres.", "error");
        }
        // Mesmo mínimo exigido pelo backend (`UserCreate.password`, ver
        // `src/app/schemas/auth.py`) - cadastrar com menos daria 422 na hora
        // de enviar, então valida aqui antes para dar um erro mais amigável.
        if (password.length < 8) {
            return RiscoIA.showMessage(msg, "A senha precisa ter pelo menos 8 caracteres.", "error");
        }
        if (password !== confirm) {
            return RiscoIA.showMessage(msg, "As senhas não coincidem.", "error");
        }

        const registerButton = registerForm.querySelector("button[type=submit]");
        registerButton && (registerButton.disabled = true);

        try {
            const response = await fetch(RiscoIA.apiUrl("/auth/register"), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password, name, email })
            });

            if (!response.ok) {
                const erro = await response.json().catch(() => null);
                throw new Error(erro?.detail || "Não foi possível concluir o cadastro.");
            }

            RiscoIA.showMessage(msg, "Cadastro realizado! Entrando no sistema...", "success");

            // A conta já foi criada no backend nesse ponto - se o login
            // automático falhar (ex.: instabilidade momentânea), não é um
            // erro de cadastro, então não cai no catch abaixo (que mostraria
            // uma mensagem enganosa dizendo que o cadastro falhou).
            try {
                await authenticate(username, password);
                setTimeout(() => { window.location.href = "index.html"; }, 500);
            } catch (loginError) {
                RiscoIA.showMessage(msg, "Cadastro realizado! Faça login para entrar.", "success");
                registerButton && (registerButton.disabled = false);
            }
        } catch (error) {
            registerButton && (registerButton.disabled = false);
            RiscoIA.showMessage(msg, error.message || "Não foi possível concluir o cadastro.", "error");
        }
    });
}

if (switchAuth) {
    const showLogin = () => {
        loginForm?.classList.remove("hidden");
        registerForm?.classList.add("hidden");
        const title = document.getElementById("formTitle");
        const subtitle = document.getElementById("formSubtitle");
        title && (title.textContent = "Acesse o sistema");
        subtitle && (subtitle.textContent = "Entre para visualizar o mapa de risco e as análises de sinistros de trânsito.");
    };
    const showRegister = () => {
        loginForm?.classList.add("hidden");
        registerForm?.classList.remove("hidden");
        const title = document.getElementById("formTitle");
        const subtitle = document.getElementById("formSubtitle");
        title && (title.textContent = "Criar sua conta");
        subtitle && (subtitle.textContent = "Cadastre seus dados para acessar o sistema de análise de risco.");
    };
    switchAuth.addEventListener("click", () => {
        loginForm?.classList.contains("hidden") ? showLogin() : showRegister();
    });
}
// OBS: o toggle de mostrar/ocultar senha (.password-toggle) é tratado apenas em
// enhancements.js, que é carregado em todas as páginas com campos de senha.
// Duplicar aqui fazia o campo alternar de tipo duas vezes por clique (um
// listener desfazendo o outro).

// ---------------------------------------------------------------------
// Proteção das páginas internas (agora respeitando expiração de sessão)
// ---------------------------------------------------------------------
const isLoginPage = location.pathname.endsWith("/login.html") || location.pathname.endsWith("/forgot-password.html");
const isProtectedPage = Boolean(document.getElementById("logoutButton") || document.getElementById("predictionForm"));

if (!isLoginPage && isProtectedPage && !RiscoIA.isSessionValid()) {
    RiscoIA.clearSession();
    window.location.replace("login.html");
}

if (!isLoginPage && isProtectedPage) {
    // Confere periodicamente se a sessão expirou enquanto a pessoa navega
    // (antes o token nunca expirava, então isso nunca era checado).
    setInterval(() => {
        if (!RiscoIA.isSessionValid()) {
            RiscoIA.clearSession();
            window.location.replace("login.html?expired=1");
        }
    }, 60000);
}

document.getElementById("logoutButton")?.addEventListener("click", () => {
    RiscoIA.clearSession();
    window.location.href = "login.html";
});

// Usuário (nome + @usuário, consistente em todas as páginas internas)
(() => {
    const user = RiscoIA.getSessionUser();
    const nameEl = document.getElementById("navUserName");
    const displayName = user && (user.name || user.username);
    if (nameEl && user) {
        nameEl.textContent = displayName + (user.username ? " • @" + user.username : "");
    }
    if (user) {
        document.title = "RiscoIA | " + displayName;
    }

    // Recursos de admin (ex.: importação de CSV) só aparecem para o
    // usuário raiz configurado via ADMIN_USERNAME/ADMIN_PASSWORD_HASH
    // (ver `src/app/core/config.py`), que é quem tem `role == "admin"`.
    if (user && user.role === "admin") {
        document.querySelectorAll("[data-admin-only]").forEach((el) => { el.hidden = false; });
    }
})();

// Menu mobile
const mobileMenu = document.getElementById("mobileMenu");
mobileMenu?.addEventListener("click", () => {
    document.querySelector(".nav-menu")?.classList.toggle("mobile-open");
});

// ---------------------------------------------------------------------
// Helpers de acesso à API
// ---------------------------------------------------------------------
async function fetchJson(path) {
    const response = await fetch(RiscoIA.apiUrl(path));
    if (!response.ok) {
        const erro = await response.json().catch(() => null);
        throw new Error(erro?.detail || "Falha ao consultar " + path);
    }
    return response.json();
}

// O modelo publicado é consultado por várias seções da página (gráfico
// mensal, metodologia); uma única requisição atende todas.
let modeloRiscoPromise = null;
function carregarModeloRisco() {
    if (!modeloRiscoPromise) modeloRiscoPromise = fetchJson("/risco/modelo");
    return modeloRiscoPromise;
}

const formatarNumero = (valor, casas = 0) =>
    Number(valor).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
const mesAno = (iso) => (iso ? iso.slice(5, 7) + "/" + iso.slice(0, 4) : "");

// ---------------------------------------------------------------------
// Mapa Leaflet: zonas de risco previstas (GET /risco/zonas)
// ---------------------------------------------------------------------
let riskMapInstance = null;
let riskZonesLayer = null;
// null = API sem modelo publicado (ou indisponível): o mapa cai nas zonas
// demonstrativas abaixo, sinalizadas como tal na legenda.
let riskZonesFeatures = null;
// Zonas por veículo já consultadas ("" = todos), para trocar o filtro sem
// repetir a requisição; e o resumo de GET /risco/veiculos (cobertura).
const riskZonesPorVeiculo = {};
let resumoVeiculos = null;

// Zonas demonstrativas, usadas só quando não há modelo publicado. `via` e
// `horario` usam o mesmo vocabulário do formulário de predição
// (RiscoIA.VIA_OPTIONS / RiscoIA.HORARIO_OPTIONS).
const zoneData = [
    { via: "francisco-junqueira", coords: [[-21.172, -47.820], [-21.168, -47.808], [-21.181, -47.804], [-21.185, -47.817]], risk: "alto", prob: 85 },
    { via: "dom-pedro", coords: [[-21.185, -47.770], [-21.178, -47.758], [-21.192, -47.754], [-21.199, -47.768]], risk: "medio", prob: 62 },
    { via: "anhanguera", coords: [[-21.214, -47.870], [-21.207, -47.846], [-21.220, -47.841], [-21.229, -47.863]], risk: "alto", prob: 78 },
    { via: "botanico", coords: [[-21.197, -47.832], [-21.190, -47.821], [-21.203, -47.814], [-21.210, -47.827]], risk: "baixo", prob: 24 },
    { via: "centro", coords: [[-21.176, -47.816], [-21.168, -47.805], [-21.179, -47.799], [-21.188, -47.810]], risk: "medio", prob: 58 }
];

const riskColors = { alto: "#ef4444", medio: "#f59e0b", baixo: "#22c55e" };

function currentZoneFilters() {
    return {
        nivel: document.getElementById("mapFilterNivel")?.value || "todos",
        soEmAlta: Boolean(document.getElementById("mapFilterEmAlta")?.checked)
    };
}

function popupZona(p) {
    const esc = RiscoIA.escapeHtml;
    const nivel = RiscoIA.levelFromApi(p.nivel_risco);
    const previsao = p.veiculo
        ? `Previsão envolvendo ${esc(RiscoIA.LABELS.veiculo[p.veiculo].toLowerCase())}: ${formatarNumero(p.acidentes_esperados)} acidentes ` +
          `(${formatarNumero(p.fracao_veiculo * 100)}% dos acidentes da zona, ${esc(p.janela_previsao)})<br>`
        : `Previsão: ${formatarNumero(p.acidentes_esperados)} acidentes (${esc(p.janela_previsao)})<br>`;
    return `<strong>${esc(p.rua_principal ? RiscoIA.formatVia(p.rua_principal) : "Região sem logradouro principal")}</strong><br>` +
        `Risco${p.veiculo ? " para " + esc(RiscoIA.LABELS.veiculo[p.veiculo].toLowerCase()) : ""}: ${nivel.toUpperCase()}<br>` +
        previsao +
        `Últimos 12 meses: ${formatarNumero(p.acidentes_12m)} acidentes` +
        (p.em_alta ? `<br><strong style="color:#ef4444">Em alta:</strong> ${formatarNumero(p.tendencia_razao, 1)}x o esperado nos últimos 6 meses` : "") +
        `<br><a href="ficha.html?celula=${encodeURIComponent(p.celula)}">Abrir ficha da zona →</a>`;
}

function renderRiskZones() {
    if (!riskMapInstance) return;
    if (riskZonesLayer) riskMapInstance.removeLayer(riskZonesLayer);
    riskZonesLayer = null;
    if (document.getElementById("toggleRiskZones")?.checked === false) return;

    if (riskZonesFeatures) {
        const filtros = currentZoneFilters();
        const visiveis = riskZonesFeatures.filter((f) => RiscoIA.zonaVisivel(f.properties, filtros));
        riskZonesLayer = L.geoJSON({ type: "FeatureCollection", features: visiveis }, {
            style(feature) {
                const cor = riskColors[RiscoIA.levelFromApi(feature.properties.nivel_risco)];
                return { color: cor, fillColor: cor, fillOpacity: 0.32, weight: feature.properties.em_alta ? 2.5 : 1 };
            },
            onEachFeature(feature, layer) {
                layer.bindPopup(popupZona(feature.properties));
            }
        });
    } else {
        riskZonesLayer = L.layerGroup(zoneData.map((z) => L.polygon(z.coords, {
            color: riskColors[z.risk], fillColor: riskColors[z.risk], fillOpacity: 0.38, weight: 2
        }).bindPopup(`<strong>${RiscoIA.LABELS.via[z.via] || z.via}</strong><br>Risco: ${z.risk.toUpperCase()} (demonstrativo)`)));
    }
    riskZonesLayer.addTo(riskMapInstance);
}

async function carregarZonasRisco() {
    const status = document.getElementById("riskZonesStatus");
    const legenda = document.getElementById("riskZonesLegendTitle");
    const veiculo = document.getElementById("mapFilterVeiculo")?.value || "";
    try {
        if (!riskZonesPorVeiculo[veiculo]) {
            const consulta = veiculo ? "/risco/zonas?veiculo=" + encodeURIComponent(veiculo) : "/risco/zonas";
            riskZonesPorVeiculo[veiculo] = (await fetchJson(consulta)).features;
        }
        const features = riskZonesPorVeiculo[veiculo];
        if (!features.length) throw new Error("sem modelo publicado");
        riskZonesFeatures = features;

        const janela = features[0].properties.janela_previsao;
        const contar = (fn) => features.filter(fn).length;
        const nomeVeiculo = veiculo ? RiscoIA.LABELS.veiculo[veiculo].toLowerCase() : "";
        if (legenda) legenda.textContent = `Zonas (previsão ${janela}${veiculo ? ", " + nomeVeiculo : ""})`;
        if (status) {
            status.textContent = veiculo
                ? `${features.length} zonas com previsão de acidentes envolvendo ${nomeVeiculo} para ${janela}: ` +
                  `${contar((f) => f.properties.nivel_risco === "ALTO")} de risco alto para ${nomeVeiculo}. ` +
                  `O tipo de veículo é informado em ${formatarNumero((resumoVeiculos?.cobertura_tipo_veiculo || 0) * 100)}% ` +
                  "dos acidentes; a previsão supõe a mesma composição nos demais."
                : `${features.length} zonas de ~550 m com previsão para ${janela}: ` +
                  `${contar((f) => f.properties.nivel_risco === "ALTO")} de risco alto, ` +
                  `${contar((f) => f.properties.em_alta)} em alta nos últimos 6 meses (base RENAEST).`;
        }
        if (!veiculo) renderZonasEmAlta(features);
    } catch (error) {
        riskZonesFeatures = null;
        if (legenda) legenda.textContent = "Zonas (demonstrativo)";
        if (status) status.textContent = "Modelo de risco ainda não publicado: exibindo zonas demonstrativas.";
    }
    renderRiskZones();
}

// Filtro "Veículo" do mapa: só aparece se o modelo publicado tiver a
// previsão por tipo de veículo (GET /risco/veiculos).
async function carregarFiltroVeiculos() {
    const select = document.getElementById("mapFilterVeiculo");
    const label = document.getElementById("mapFilterVeiculoLabel");
    if (!select || !label) return;
    try {
        resumoVeiculos = await fetchJson("/risco/veiculos");
        resumoVeiculos.veiculos.forEach((v) => {
            const option = document.createElement("option");
            option.value = v.veiculo;
            option.textContent = `${RiscoIA.LABELS.veiculo[v.veiculo]} (${formatarNumero(v.fracao_cidade * 100)}% dos acidentes)`;
            select.appendChild(option);
        });
        label.hidden = false;
        select.addEventListener("change", carregarZonasRisco);
    } catch (error) {
        // Sem previsão por veículo: o filtro continua oculto.
    }
}

// Painel "Zonas em alta" do monitoramento: só aparece quando o modelo
// publicado tem pelo menos uma zona com tendência de alta significativa.
function renderZonasEmAlta(features) {
    const panel = document.getElementById("hotZonesPanel");
    const lista = document.getElementById("hotZonesList");
    if (!panel || !lista) return;
    const quentes = features
        .filter((f) => f.properties.em_alta)
        .sort((a, b) => b.properties.tendencia_razao - a.properties.tendencia_razao);
    if (!quentes.length) return;

    document.getElementById("hotZonesTitle").textContent =
        quentes.length === 1 ? "1 zona em alta" : `${quentes.length} zonas em alta`;
    lista.innerHTML = quentes.slice(0, 5).map((f) => {
        const p = f.properties;
        const nome = p.rua_principal ? RiscoIA.formatVia(p.rua_principal) : "Região sem logradouro principal";
        return `<li><span>${RiscoIA.escapeHtml(nome)}</span><strong>${formatarNumero(p.tendencia_razao, 1)}x</strong></li>`;
    }).join("");
    panel.hidden = false;
}

function initRiskMap() {
    const el = document.getElementById("riskMap");
    if (!el || typeof L === "undefined") return;

    const loadingEl = document.getElementById("mapLoadingState");
    if (loadingEl) loadingEl.hidden = false;

    riskMapInstance = L.map(el, { zoomControl: false }).setView([-21.1775, -47.8103], 12);

    // Salvaguarda: se a barra de controles/cabeçalho ainda não tinha a
    // altura final quando o Leaflet mediu o container (ex.: fonte
    // carregando), o mapa nasce com o tamanho errado. invalidateSize()
    // depois do primeiro layout corrige isso sem custo perceptível.
    setTimeout(() => riskMapInstance?.invalidateSize(), 150);

    const tileLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "© OpenStreetMap contributors"
    }).addTo(riskMapInstance);

    // Estado de carregamento do mapa: os tiles do OpenStreetMap dependem de
    // uma requisição de rede que pode demorar ou falhar (bloqueio de rede,
    // sem internet). Antes não havia nenhum feedback visual disso.
    if (loadingEl) {
        tileLayer.on("load", () => { loadingEl.hidden = true; });
        tileLayer.on("tileerror", () => {
            loadingEl.textContent = "Não foi possível carregar os mapas (verifique sua conexão).";
        });
    }

    L.control.zoom({ position: "topright" }).addTo(riskMapInstance);
    carregarZonasRisco();
    carregarFiltroVeiculos();
    carregarSinistrosReais();

    ["toggleRiskZones", "mapFilterNivel", "mapFilterEmAlta"].forEach((id) => {
        document.getElementById(id)?.addEventListener("change", renderRiskZones);
    });
    document.getElementById("toggleRealData")?.addEventListener("change", (e) => {
        if (!sinistrosLayer) return;
        if (e.target.checked) sinistrosLayer.addTo(riskMapInstance);
        else riskMapInstance.removeLayer(sinistrosLayer);
    });
    document.getElementById("realDataMode")?.addEventListener("change", (e) => {
        realDataMode = e.target.value;
        renderSinistrosReais();
    });

    // Expandir: o mapa sai da coluna estreita ao lado do texto do hero e
    // passa a ocupar a largura cheia, abaixo do título (ver .hero-grid.map-expanded
    // em style.css). O Leaflet não percebe sozinho que o container mudou de
    // tamanho via CSS, por isso o invalidateSize() depois do toggle.
    const expandButton = document.getElementById("toggleMapExpand");
    const heroGrid = document.getElementById("heroGrid");
    expandButton?.addEventListener("click", () => {
        if (!heroGrid) return;
        const expanded = heroGrid.classList.toggle("map-expanded");
        expandButton.textContent = expanded ? "✕ Recolher" : "⛶ Expandir";
        expandButton.setAttribute("aria-pressed", String(expanded));
        requestAnimationFrame(() => riskMapInstance?.invalidateSize());
    });
}

// ---------------------------------------------------------------------
// Sinistros reais (GET /sinistros/geojson) - camada complementar às zonas
// de risco previstas acima. Os pontos abaixo são os sinistros já ingeridos
// no banco a partir dos CSVs oficiais.
// Três modos de exibição sobre os mesmos dados (RiscoIA.CONFIG não guarda
// isso porque é estado só desta página, não configuração compartilhada).
// ---------------------------------------------------------------------
const GRAVIDADE_CORES = { fatal: "#d03b3b", grave: "#ec835a", leve: "#fab219", ileso: "#0ca30c", nao_informado: "#8a94a3" };
const GRAVIDADE_PESOS_CALOR = { fatal: 4, grave: 2, leve: 1, ileso: 0.3, nao_informado: 0.2 };
let sinistrosFeatures = [];
let sinistrosLayer = null;
let realDataMode = "heat"; // padrão: mapa de calor

function gravidadeDoSinistro(props) {
    if (props.qtd_gravidade_fatal > 0) return "fatal";
    if (props.qtd_gravidade_grave > 0) return "grave";
    if (props.qtd_gravidade_leve > 0) return "leve";
    if (props.qtd_gravidade_ileso > 0) return "ileso";
    return "nao_informado";
}

function construirCamadaCalor(features) {
    const pontos = features.map((f) => {
        const [lon, lat] = f.geometry.coordinates;
        return [lat, lon, GRAVIDADE_PESOS_CALOR[gravidadeDoSinistro(f.properties)]];
    });
    return L.heatLayer(pontos, { radius: 28, blur: 22, max: 3, maxZoom: 15 });
}

function construirCamadaPontosOuMarcadores(features, modo) {
    return L.geoJSON({ type: "FeatureCollection", features }, {
        pointToLayer(feature, latlng) {
            if (modo === "markers") return L.marker(latlng);
            const sev = gravidadeDoSinistro(feature.properties);
            return L.circleMarker(latlng, {
                radius: 4,
                color: "#141414",
                weight: 1,
                fillColor: GRAVIDADE_CORES[sev],
                fillOpacity: 0.85
            });
        },
        onEachFeature(feature, layer) {
            const p = feature.properties;
            const sev = gravidadeDoSinistro(p);
            layer.bindTooltip(
                `<strong>${p.logradouro || "Via não informada"}</strong><br>` +
                `${p.data || "data não informada"}${p.turno ? " · " + p.turno : ""}<br>` +
                `Gravidade: ${sev.replace("_", " ")}`,
                { sticky: true, direction: "top" }
            );
        }
    });
}

// Reconstrói a camada a partir dos dados já em memória (sinistrosFeatures) -
// chamada tanto depois do fetch quanto ao trocar o modo de exibição, sem
// precisar consultar a API de novo.
function renderSinistrosReais() {
    if (sinistrosLayer && riskMapInstance) riskMapInstance.removeLayer(sinistrosLayer);
    sinistrosLayer = null;
    if (!riskMapInstance || !sinistrosFeatures.length) return;

    sinistrosLayer = realDataMode === "heat"
        ? construirCamadaCalor(sinistrosFeatures)
        : construirCamadaPontosOuMarcadores(sinistrosFeatures, realDataMode);

    if (document.getElementById("toggleRealData")?.checked !== false) {
        sinistrosLayer.addTo(riskMapInstance);
    }
}

// Últimos 12 meses da base: o histórico completo (2015+) tem dezenas de
// milhares de pontos e, antes de 2019, só os sinistros fatais.
async function periodoRecente() {
    const { data_fim: fim } = await fetchJson("/analise/resumo");
    if (!fim) return null;
    const inicio = new Date(fim);
    inicio.setFullYear(inicio.getFullYear() - 1);
    inicio.setDate(inicio.getDate() + 1);
    return { data_inicio: inicio.toISOString().slice(0, 10), data_fim: fim };
}

async function carregarSinistrosReais() {
    const status = document.getElementById("realDataStatus");
    try {
        const periodo = await periodoRecente();
        if (!periodo) throw new Error("sem sinistros");
        const params = new URLSearchParams({ ...periodo, recentes_primeiro: true, limit: 20000 });
        const geojson = await fetchJson("/sinistros/geojson?" + params.toString());

        sinistrosFeatures = geojson.features;
        renderSinistrosReais();

        if (status) {
            status.textContent = sinistrosFeatures.length
                ? `${formatarNumero(sinistrosFeatures.length)} sinistros reais com coordenada nos últimos 12 meses (até ${mesAno(periodo.data_fim)}, InfoSiga/Detran-SP).`
                : "Nenhum sinistro geocodificado disponível ainda na base.";
        }

        // Os gráficos do topo descrevem o mesmo período, agregados na API
        // (a camada do mapa só tem os sinistros com coordenada).
        const filtro = new URLSearchParams(periodo).toString();
        const [turnos, vias] = await Promise.all([
            fetchJson("/analise/distribuicao?dimensao=turno&" + filtro),
            fetchJson("/analise/vias?limit=8&" + filtro)
        ]);
        const nomesTurno = { MADRUGADA: "Madrugada", MANHA: "Manhã", TARDE: "Tarde", NOITE: "Noite" };
        window.RiscoIACharts?.updateReal({
            periodData: Object.fromEntries(turnos.filter((t) => nomesTurno[t.chave]).map((t) => [nomesTurno[t.chave], t.sinistros])),
            roadsData: Object.fromEntries(vias.map((v) => [RiscoIA.formatVia(v.via), v.sinistros]))
        });
    } catch (error) {
        if (status) status.textContent = "Não foi possível carregar os sinistros reais agora.";
        window.RiscoIACharts?.updateReal(null);
    }
}

// ---------------------------------------------------------------------
// Gráficos Chart.js - "Sinistros por período" e "Vias com maior
// incidência" descrevem dados reais dos últimos 12 meses (GET
// /analise/distribuicao e /analise/vias, ver carregarSinistrosReais acima),
// não previsões. Um conjunto demonstrativo
// só aparece enquanto os dados reais não chegam (carregando) ou se a
// consulta falhar.
// ---------------------------------------------------------------------
let periodChartInstance = null;
let roadsChartInstance = null;

const DEMO_PERIOD_DATA = { Manhã: 28, Tarde: 24, Noite: 38, Madrugada: 10 };
const DEMO_ROADS_DATA = zoneData.reduce((acc, z) => {
    acc[RiscoIA.LABELS.via[z.via] || z.via] = z.prob;
    return acc;
}, {});

function initCharts() {
    if (typeof Chart === "undefined") return;

    const p = document.getElementById("periodChart");
    const r = document.getElementById("roadsChart");

    if (p) {
        periodChartInstance = new Chart(p, {
            type: "doughnut",
            data: {
                labels: Object.keys(DEMO_PERIOD_DATA),
                datasets: [{ data: Object.values(DEMO_PERIOD_DATA) }]
            },
            options: { responsive: true, plugins: { legend: { position: "bottom" } } }
        });
    }

    if (r) {
        roadsChartInstance = new Chart(r, {
            type: "bar",
            data: {
                labels: Object.keys(DEMO_ROADS_DATA),
                datasets: [{ label: "Sinistros", data: Object.values(DEMO_ROADS_DATA) }]
            },
            options: { responsive: true, scales: { y: { beginAtZero: true } } }
        });
    }

    // Exposto para carregarSinistrosReais() atualizar os gráficos assim que
    // a consulta a /sinistros/geojson responder, sem repetir a montagem do
    // Chart.js.
    window.RiscoIACharts = {
        updateReal(computed) {
            const periodData = computed ? computed.periodData : DEMO_PERIOD_DATA;
            const roadsData = computed ? computed.roadsData : DEMO_ROADS_DATA;

            if (periodChartInstance) {
                periodChartInstance.data.labels = Object.keys(periodData);
                periodChartInstance.data.datasets[0].data = Object.values(periodData);
                periodChartInstance.update();
            }
            if (roadsChartInstance) {
                roadsChartInstance.data.labels = Object.keys(roadsData);
                roadsChartInstance.data.datasets[0].data = Object.values(roadsData);
                roadsChartInstance.data.datasets[0].label = computed ? "Sinistros" : "Sinistros (demonstrativo)";
                roadsChartInstance.update();
            }
        }
    };
}

// ---------------------------------------------------------------------
// Predição: GET /risco/simular (previsão de 12 meses da via x perfil de
// dia/hora dela). A heurística local RiscoIA.calculateFallback só entra se
// não houver modelo publicado ou a API estiver fora do ar, e o resultado
// avisa quando isso acontece.
// ---------------------------------------------------------------------
function updateResult(valor, factors, meta, opcoes = {}) {
    const card = document.getElementById("predictionResult");
    const tag = document.getElementById("riskTag");
    const title = document.getElementById("riskTitle");
    const percent = document.getElementById("riskPercent");
    const meter = document.getElementById("riskMeter");
    const why = document.getElementById("riskFactors");
    if (!card) return;

    const level = opcoes.nivel || RiscoIA.levelFromProb(valor);
    tag.textContent = level === "alto" ? "RISCO ELEVADO" : level === "medio" ? "RISCO MÉDIO" : "RISCO BAIXO";
    card.className = `result-card ${level}`;
    percent.textContent = opcoes.rotulo || `${valor}% de probabilidade de sinistro`;
    title.textContent = level === "alto" ? "Atenção recomendada" : level === "medio" ? "Atenção moderada" : "Condição de menor risco";
    why.textContent = factors;
    meter.style.width = valor + "%";
    const nota = document.getElementById("riskNote");
    if (nota) nota.textContent = opcoes.nota || "Estimativa demonstrativa do frontend (sem modelo de risco publicado no backend).";
    card.hidden = false;

    // Em vez de um MutationObserver "espionando" o DOM para descobrir que
    // uma previsão aconteceu, disparamos um evento explícito com os dados -
    // enhancements.js escuta esse evento para salvar o histórico.
    document.dispatchEvent(new CustomEvent("riscoia:prediction", {
        detail: { probabilidade: valor, risco: level, ...meta }
    }));
}

async function simularNaApi(via, horario, dia) {
    const params = new URLSearchParams({ via, dia_semana: RiscoIA.diaSemanaIndex(dia) });
    RiscoIA.HORARIO_HORAS[horario].forEach((h) => params.append("horas", h));
    return fetchJson("/risco/simular?" + params.toString());
}

async function handlePrediction(e) {
    e.preventDefault();

    const viaSelect = document.getElementById("predVia");
    const via = viaSelect.value;
    const horario = document.getElementById("predHorario").value;
    const clima = document.getElementById("predClima").value;
    const dia = document.getElementById("predDia").value;

    const btn = document.getElementById("calculateRisk");
    const txt = document.getElementById("predictionButtonText");
    const spin = document.getElementById("predictionSpinner");
    const err = document.getElementById("predictionError");
    if (!via || !horario || !clima || !dia) return;

    err.hidden = true;
    btn.disabled = true;
    txt.textContent = "Analisando dados...";
    spin?.classList.remove("hidden");

    try {
        if (viaSelect.dataset.fonte === "api") {
            try {
                const r = await simularNaApi(via, horario, dia);
                const esperado = formatarNumero(r.acidentes_esperados_janela, 1);
                updateResult(
                    r.indice,
                    `Esperados ${esperado} acidentes por ano nessa via ${RiscoIA.diaNoPlural(dia)}, nesse horário. ` + r.fatores.join(" "),
                    { via, horario, clima, dia, origem: "Modelo RiscoIA" },
                    {
                        nivel: RiscoIA.levelFromApi(r.nivel_risco),
                        rotulo: `Índice de risco ${r.indice}/100`,
                        nota: `Modelo publicado: previsão de 12 meses da via (${r.janela_previsao}) combinada com o perfil de dia e hora dela. O índice compara com todas as vias e horas da semana.`
                    }
                );
                return;
            } catch (error) {
                err.textContent = "Não foi possível consultar o modelo agora; o resultado abaixo é a estimativa demonstrativa do frontend.";
                err.hidden = false;
            }
        }

        const prob = RiscoIA.calculateFallback({ via, horario, clima, dia });
        const climaTexto = clima === "chuva" ? "Chuva intensa" : "Condição climática favorável";
        const horarioTexto = (horario === "pico-manha" || horario === "pico-noite") ? "horário de pico" : "horário fora do pico";
        updateResult(
            prob,
            `Fator principal: ${climaTexto} + ${horarioTexto}. Estimativa demonstrativa do frontend (sem modelo de risco publicado no backend).`,
            { via, horario, clima, dia, origem: "Frontend demonstrativo" }
        );
    } finally {
        btn.disabled = false;
        txt.textContent = "Calcular Risco";
        spin?.classList.add("hidden");
    }
}

// Troca as 5 vias fixas do <select> pelas vias reais do ranking
// (GET /risco/vias). Sem modelo publicado, as opções fixas continuam e a
// simulação usa a heurística demonstrativa.
async function carregarViasSimulacao() {
    const select = document.getElementById("predVia");
    if (!select) return;
    try {
        const vias = await fetchJson("/risco/vias?limit=300");
        if (!vias.length) return;
        const atual = new URLSearchParams(location.search).get("via") || select.value;
        select.innerHTML = '<option value="">Selecione</option>' + vias.map((v) =>
            `<option value="${RiscoIA.escapeHtml(v.via)}">${RiscoIA.escapeHtml(RiscoIA.formatVia(v.via))}</option>`
        ).join("");
        select.dataset.fonte = "api";
        if (vias.some((v) => v.via === atual)) select.value = atual;
        select.dispatchEvent(new Event("change"));
    } catch (error) {
        // Mantém as vias demonstrativas do HTML.
    }
}

const predictionForm = document.getElementById("predictionForm");
if (predictionForm) {
    const selects = ["predVia", "predHorario", "predClima", "predDia"].map((id) => document.getElementById(id));
    const button = document.getElementById("calculateRisk");
    const validate = () => { button.disabled = !selects.every((s) => s && s.value); };
    selects.forEach((s) => s?.addEventListener("change", validate));
    validate();
    predictionForm.addEventListener("submit", handlePrediction);
}

// Botão "usar condições de agora": preenche horário e dia a partir do
// relógio do dispositivo e o clima a partir de uma consulta real à
// Open-Meteo (API pública, sem chave). Não deixa os sinistros do InfoSiga
// "em tempo real" (isso não existe, o InfoSiga só publica mensalmente),
// mas deixa a simulação usando as condições reais deste exato momento.
const liveConditionsButton = document.getElementById("useLiveConditions");
if (liveConditionsButton) {
    const liveText = document.getElementById("liveConditionsText");
    const liveSpinner = document.getElementById("liveConditionsSpinner");
    const err = document.getElementById("predictionError");

    liveConditionsButton.addEventListener("click", async () => {
        liveConditionsButton.disabled = true;
        liveSpinner?.classList.remove("hidden");
        err.hidden = true;

        const now = new Date();
        document.getElementById("predHorario").value = RiscoIA.horarioAtualBucket(now);
        document.getElementById("predDia").value = RiscoIA.diaAtualPtBR(now);

        try {
            document.getElementById("predClima").value = await RiscoIA.fetchLiveWeatherClima();
        } catch (error) {
            // Sem conexão com a Open-Meteo: mantém o preenchimento de
            // horário/dia (que não depende de rede) e avisa sobre o clima.
            err.textContent = "Não foi possível consultar o clima atual agora; horário e dia foram preenchidos, selecione o clima manualmente.";
            err.hidden = false;
        }

        ["predVia", "predHorario", "predClima", "predDia"].forEach((id) => {
            document.getElementById(id)?.dispatchEvent(new Event("change"));
        });
        // Se a via ainda não foi escolhida, o botão de calcular continua
        // desabilitado até a pessoa selecionar - de propósito, não escolhemos
        // uma via por ela.

        liveConditionsButton.disabled = false;
        liveSpinner?.classList.add("hidden");
    });
}

// ---------------------------------------------------------------------
// Widget "Risco agora" do dashboard: as vias de maior risco no dia e hora
// do relógio de quem está vendo (GET /risco/agora). O clima ao vivo
// (Open-Meteo) é exibido, mas não entra no cálculo (a base não tem como
// medir o efeito da chuva). Sem modelo publicado, cai na heurística local.
// ---------------------------------------------------------------------
async function renderLiveRisk() {
    const grid = document.getElementById("liveRiskGrid");
    const title = document.getElementById("liveRiskTitle");
    const badge = document.getElementById("liveRiskBadge");
    if (!grid) return;

    const now = new Date();
    const horario = RiscoIA.horarioAtualBucket(now);
    const dia = RiscoIA.diaAtualPtBR(now);
    let clima = "sol";
    let climaOrigem = "estimativa (sem conexão com a Open-Meteo)";
    try {
        clima = await RiscoIA.fetchLiveWeatherClima();
        climaOrigem = "Open-Meteo";
    } catch (error) {
        // Mantém o painel funcionando mesmo sem internet, só avisa a origem do dado de clima.
    }

    let resultados;
    try {
        const params = new URLSearchParams({ dia_semana: RiscoIA.diaSemanaIndex(dia), hora: now.getHours(), limit: 5 });
        const itens = await fetchJson("/risco/agora?" + params.toString());
        resultados = itens.map((i) => ({
            via: RiscoIA.formatVia(i.via), valor: i.indice, texto: `${i.indice}/100`, nivel: RiscoIA.levelFromApi(i.nivel_risco),
            detalhe: `${formatarNumero(i.intensidade, 1)}x a média por hora da via`
        }));
        title.textContent = `${dia}, ${String(now.getHours()).padStart(2, "0")}h · ${RiscoIA.LABELS.clima[clima]} (${climaOrigem}, não entra no cálculo)`;
    } catch (error) {
        resultados = zoneData
            .map((z) => {
                const prob = RiscoIA.calculateFallback({ via: z.via, horario, clima, dia });
                return { via: RiscoIA.LABELS.via[z.via] || z.via, valor: prob, texto: `${prob}%`, nivel: RiscoIA.levelFromProb(prob) };
            })
            .sort((a, b) => b.valor - a.valor);
        title.textContent = `${dia}, ${RiscoIA.LABELS.horario[horario]} · ${RiscoIA.LABELS.clima[clima]} (${climaOrigem}) · demonstrativo`;
    }
    if (!resultados.length) return;

    const piorNivel = resultados[0].nivel;
    badge.textContent = "RISCO " + piorNivel.toUpperCase();
    badge.className = "smart-badge " + ({ alto: "high", medio: "medium", baixo: "low" }[piorNivel] || "neutral");

    grid.innerHTML = resultados.map((r) =>
        `<div class="live-risk-item ${r.nivel}"><span class="live-risk-via">${RiscoIA.escapeHtml(r.via)}</span><span class="live-risk-value">${r.texto}</span>` +
        (r.detalhe ? `<span class="live-risk-detail">${r.detalhe}</span>` : "") + "</div>"
    ).join("");
}

document.getElementById("refreshLiveRisk")?.addEventListener("click", renderLiveRisk);

// ---------------------------------------------------------------------
// "Áreas que merecem atenção": aglomerados de acidentes com óbito
// (GET /risco/pontos-criticos), completados com zonas em alta quando há
// menos de 3 pontos críticos. Sem modelo publicado, os cartões
// demonstrativos do HTML continuam.
// ---------------------------------------------------------------------
function cartaoAlerta(classe, tag, titulo, texto, meta, link) {
    const esc = RiscoIA.escapeHtml;
    return `<article class="risk-alert ${classe}"><span class="risk-alert-tag">${esc(tag)}</span>` +
        `<h3>${esc(titulo)}</h3><p>${esc(texto)}</p><span class="risk-alert-meta">${esc(meta)}</span>` +
        (link ? `<a class="risk-alert-link" href="${link}">Abrir ficha →</a>` : "") + "</article>";
}

async function carregarAlertas() {
    const grid = document.getElementById("riskAlertGrid");
    if (!grid) return;
    try {
        const [pontos, zonas] = await Promise.all([
            fetchJson("/risco/pontos-criticos?limit=3"),
            fetchJson("/risco/zonas?em_alta=true")
        ]);
        const cartoes = pontos.map((p) => cartaoAlerta(
            "high",
            `PONTO CRÍTICO · ${p.n_obitos} ${p.n_obitos === 1 ? "ÓBITO" : "ÓBITOS"}`,
            p.rua_principal ? RiscoIA.formatVia(p.rua_principal) : "Local sem logradouro informado",
            `${p.n_acidentes_fatais} acidentes com óbito num raio de ~${formatarNumero(p.raio_m)} m, entre ${mesAno(p.primeiro)} e ${mesAno(p.ultimo)}.`,
            "Aglomerado de acidentes fatais (DBSCAN), 2023 em diante",
            p.rua_principal ? "ficha.html?via=" + encodeURIComponent(p.rua_principal) : null
        ));
        zonas.features
            .sort((a, b) => b.properties.tendencia_razao - a.properties.tendencia_razao)
            .slice(0, Math.max(0, 3 - cartoes.length))
            .forEach((f) => {
                const z = f.properties;
                cartoes.push(cartaoAlerta(
                    "medium", "ZONA EM ALTA",
                    z.rua_principal ? RiscoIA.formatVia(z.rua_principal) : "Região sem logradouro principal",
                    `Nos últimos 6 meses, ${formatarNumero(z.tendencia_razao, 1)}x os acidentes que o histórico da região indicava.`,
                    `Previsão: ${formatarNumero(z.acidentes_esperados)} acidentes em ${z.janela_previsao}`,
                    "ficha.html?celula=" + encodeURIComponent(z.celula)
                ));
            });
        if (!cartoes.length) return;
        grid.innerHTML = cartoes.join("");
        const subtitulo = document.getElementById("riskAlertsSubtitle");
        if (subtitulo) subtitulo.textContent = "Locais com acidentes fatais recorrentes na base oficial (RENAEST), do mais para o menos letal.";
    } catch (error) {
        // Sem modelo publicado: mantém os cartões demonstrativos.
    }
}

// ---------------------------------------------------------------------
// Previsão mensal da cidade (GET /risco/previsao-mensal): histórico real
// desde 2023 + próximos 12 meses com faixa de 95%.
// ---------------------------------------------------------------------
async function carregarPrevisaoMensal() {
    const card = document.getElementById("monthlyChartCard");
    const canvas = document.getElementById("monthlyChart");
    if (!card || !canvas || typeof Chart === "undefined") return;
    try {
        const meses = (await fetchJson("/risco/previsao-mensal")).filter((m) => m.mes >= "2023-01");
        if (!meses.some((m) => m.futuro)) return;
        card.hidden = false;

        const ultimoReal = meses.filter((m) => !m.futuro).pop();
        const futuro = (campo) => meses.map((m) => (m.futuro ? m[campo] : m === ultimoReal ? m.real : null));
        new Chart(canvas, {
            type: "line",
            data: {
                labels: meses.map((m) => mesAno(m.mes + "-01")),
                datasets: [
                    { label: "Real", data: meses.map((m) => m.real), borderColor: "#38bdf8", backgroundColor: "#38bdf8", spanGaps: false, tension: 0.2 },
                    { label: "Previsto", data: futuro("previsto"), borderColor: "#f59e0b", borderDash: [6, 4], pointRadius: 2, tension: 0.2 },
                    { label: "Limite inferior (95%)", data: futuro("limite_inferior"), borderColor: "transparent", pointRadius: 0 },
                    { label: "Faixa de 95%", data: futuro("limite_superior"), borderColor: "transparent", backgroundColor: "rgba(245,158,11,.16)", pointRadius: 0, fill: "-1" }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "bottom", labels: { filter: (item) => item.text !== "Limite inferior (95%)" } } },
                scales: { y: { beginAtZero: true, title: { display: true, text: "Acidentes no mês" } } }
            }
        });

        const nota = document.getElementById("monthlyChartNote");
        const total = meses.filter((m) => m.futuro).reduce((acc, m) => acc + m.previsto, 0);
        let texto = `Previsão de ${formatarNumero(total)} acidentes nos próximos 12 meses (base RENAEST, toda a cidade). ` +
            "Meses sem dados na fonte aparecem como falha na linha.";
        try {
            const sm = (await carregarModeloRisco()).metricas.serie_mensal;
            texto += ` No backtest, o modelo errou em média ${formatarNumero(sm.mape_modelo)}% por mês, contra ` +
                `${formatarNumero(sm.mape_mesmo_mes_ano_anterior)}% de repetir o mesmo mês do ano anterior.`;
        } catch (error) {
            // Sem métricas: mostra só a previsão.
        }
        if (nota) nota.textContent = texto;
    } catch (error) {
        // Sem modelo publicado: o cartão continua oculto.
    }
}

// ---------------------------------------------------------------------
// Metodologia: o que foi publicado e como o modelo se saiu no backtest
// (GET /risco/modelo), incluindo quando a média histórica vence o ML.
// ---------------------------------------------------------------------
const NOMES_MODELO = {
    BASE_taxa: "média histórica por célula",
    BASE_EB: "média histórica suavizada pela vizinhança",
    GBM: "gradient boosting (Poisson)",
    MISTO_GBM_EB: "combinação de gradient boosting e média suavizada"
};

async function carregarInfoModelo() {
    const box = document.getElementById("modelInfo");
    if (!box) return;
    try {
        const m = await carregarModeloRisco();
        const backtest = Object.fromEntries(m.metricas.ocorrencia_backtest.map((r) => [r.modelo, r]));
        const escolhido = backtest[m.modelo_ocorrencia];
        const gbm = backtest.GBM;
        const sm = m.metricas.serie_mensal;
        const limpeza = m.resumo_limpeza;
        const pct = (x) => formatarNumero(x * 100) + "%";

        document.getElementById("modelInfoTitle").textContent =
            `Gerado em ${new Date(m.gerado_em).toLocaleDateString("pt-BR")} a partir de ${m.fonte}`;
        const itens = [
            `Zonas: previsão de acidentes por célula de ~550 m para ${m.janela_previsao}. Escolhido no backtest: ${NOMES_MODELO[m.modelo_ocorrencia] || m.modelo_ocorrencia}.`,
            `As 5% de células com maior previsão concentraram ${pct(escolhido.captura_top5pct)} dos acidentes dos 12 meses seguintes (média dos cortes do backtest).`,
            m.modelo_ocorrencia === "GBM"
                ? `O gradient boosting venceu as médias históricas no desvio de Poisson (${formatarNumero(gbm.dev_poisson, 2)}).`
                : `O gradient boosting não superou a escolha (${formatarNumero(gbm.dev_poisson, 2)} contra ${formatarNumero(escolhido.dev_poisson, 2)} de desvio de Poisson): o histórico de cada região já explica quase tudo.`,
            `Previsão mensal da cidade: erro médio de ${formatarNumero(sm.mape_modelo)}% por mês, contra ${formatarNumero(sm.mape_mesmo_mes_ano_anterior)}% de repetir o mesmo mês do ano anterior.`,
            `Limpeza: ${formatarNumero(limpeza.coord_valida)} acidentes com coordenada válida desde 2023; ${formatarNumero(limpeza.em_placeholder)} em coordenadas genéricas de rodovia foram descartados` +
                (limpeza.meses_ausentes.length ? `; meses sem dados na fonte: ${limpeza.meses_ausentes.join(", ")}.` : ".")
        ];
        document.getElementById("modelInfoList").innerHTML = itens.map((t) => `<li>${RiscoIA.escapeHtml(t)}</li>`).join("");
        box.hidden = false;
    } catch (error) {
        // Sem modelo publicado: a metodologia fica só com os passos gerais.
    }
}

// ---------------------------------------------------------------------
// Importação de CSV (POST /ingest/csv) - só aparece para o admin raiz
// (ver o bloco "Recursos de admin" mais acima, que revela [data-admin-only]
// quando RiscoIA.getSessionUser().role === "admin"). A rota já valida o
// papel no backend; esconder o formulário para quem não é admin é só UX.
// ---------------------------------------------------------------------
function initAdminImport() {
    const form = document.getElementById("adminImportForm");
    if (!form) return;

    const fileInput = document.getElementById("adminCsvFile");
    const button = document.getElementById("adminImportButton");
    const status = document.getElementById("adminImportStatus");

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const file = fileInput.files[0];
        if (!file) return;

        button.disabled = true;
        RiscoIA.showMessage(status, "Importando " + file.name + "...", "info");

        try {
            const body = new FormData();
            body.append("file", file);
            const response = await fetch(RiscoIA.apiUrl("/ingest/csv"), {
                method: "POST",
                headers: RiscoIA.authHeader(),
                body
            });
            const result = await response.json().catch(() => null);
            if (!response.ok) {
                throw new Error(result?.detail || "Falha ao importar o CSV.");
            }
            RiscoIA.showMessage(
                status,
                `Importado: ${result.inserted} novo(s), ${result.updated} atualizado(s), ` +
                `${result.skipped_other_municipio} fora do município, ${result.skipped_invalid} inválido(s).`,
                "success"
            );
            form.reset();
            carregarSinistrosReais();
        } catch (error) {
            RiscoIA.showMessage(status, error.message, "error");
        } finally {
            button.disabled = false;
        }
    });
}

document.addEventListener("DOMContentLoaded", () => {
    initRiskMap();
    initCharts();
    renderLiveRisk();
    initAdminImport();
    carregarAlertas();
    carregarPrevisaoMensal();
    carregarInfoModelo();
    carregarViasSimulacao();
});
