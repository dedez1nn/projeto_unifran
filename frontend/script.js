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
// Mapa Leaflet com zonas e filtros
// ---------------------------------------------------------------------
let riskMapInstance = null;
let riskLayers = [];

// Dados demonstrativos. `via` e `horario` usam o MESMO vocabulário do
// formulário de predição (RiscoIA.VIA_OPTIONS / RiscoIA.HORARIO_OPTIONS),
// então o nome exibido em qualquer lugar do site vem sempre de
// RiscoIA.LABELS, e não pode mais ficar dessincronizado entre telas.
const zoneData = [
    { via: "francisco-junqueira", coords: [[-21.172, -47.820], [-21.168, -47.808], [-21.181, -47.804], [-21.185, -47.817]], risk: "alto", horario: "pico-noite", clima: "chuva", veiculo: "carro", prob: 85 },
    { via: "dom-pedro", coords: [[-21.185, -47.770], [-21.178, -47.758], [-21.192, -47.754], [-21.199, -47.768]], risk: "medio", horario: "pico-manha", clima: "sol", veiculo: "moto", prob: 62 },
    { via: "anhanguera", coords: [[-21.214, -47.870], [-21.207, -47.846], [-21.220, -47.841], [-21.229, -47.863]], risk: "alto", horario: "fora-pico", clima: "chuva", veiculo: "carro", prob: 78 },
    { via: "botanico", coords: [[-21.197, -47.832], [-21.190, -47.821], [-21.203, -47.814], [-21.210, -47.827]], risk: "baixo", horario: "fora-pico", clima: "sol", veiculo: "onibus", prob: 24 },
    { via: "centro", coords: [[-21.176, -47.816], [-21.168, -47.805], [-21.179, -47.799], [-21.188, -47.810]], risk: "medio", horario: "pico-manha", clima: "sol", veiculo: "moto", prob: 58 }
];

const riskColors = { alto: "#ef4444", medio: "#f59e0b", baixo: "#22c55e" };

function currentMapFilters() {
    return {
        horario: document.getElementById("mapFilterHorario")?.value || "todos",
        clima: document.getElementById("mapFilterClima")?.value || "todos",
        veiculo: document.getElementById("mapFilterVeiculo")?.value || "todos"
    };
}

function renderRiskMap() {
    if (!riskMapInstance) return;
    riskLayers.forEach((l) => l.remove());
    riskLayers = [];

    const filters = currentMapFilters();
    zoneData.filter((z) => RiscoIA.zoneMatches(z, filters)).forEach((z) => {
        const name = RiscoIA.LABELS.via[z.via] || z.via;
        const layer = L.polygon(z.coords, {
            color: riskColors[z.risk],
            fillColor: riskColors[z.risk],
            fillOpacity: 0.38,
            weight: 2
        }).bindPopup(`<strong>${name}</strong><br>Risco: ${z.risk.toUpperCase()}<br>Probabilidade estimada: ${z.prob}%`);
        layer.addTo(riskMapInstance);
        riskLayers.push(layer);
    });
}

function initRiskMap() {
    const el = document.getElementById("riskMap");
    if (!el || typeof L === "undefined") return;

    const loadingEl = document.getElementById("mapLoadingState");
    if (loadingEl) loadingEl.hidden = false;

    riskMapInstance = L.map(el, { zoomControl: false }).setView([-21.1775, -47.8103], 12);

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
    renderRiskMap();
    carregarSinistrosReais();

    ["mapFilterHorario", "mapFilterClima", "mapFilterVeiculo"].forEach((id) => {
        document.getElementById(id)?.addEventListener("change", renderRiskMap);
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
// de risco acima, que continuam sendo uma simulação demonstrativa (o
// projeto ainda não tem um modelo de predição real, ver README). Os pontos
// abaixo são os sinistros já ingeridos no banco a partir dos CSVs oficiais.
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

async function carregarSinistrosReais() {
    const status = document.getElementById("realDataStatus");
    try {
        const response = await fetch(RiscoIA.apiUrl("/sinistros/geojson?limit=1500"));
        if (!response.ok) throw new Error("Falha ao consultar sinistros");
        const geojson = await response.json();

        sinistrosFeatures = geojson.features;
        renderSinistrosReais();

        if (status) {
            status.textContent = sinistrosFeatures.length
                ? `${sinistrosFeatures.length} sinistros reais carregados (Infosiga/Detran-SP).`
                : "Nenhum sinistro geocodificado disponível ainda na base.";
        }

        window.RiscoIACharts?.updateReal(computeChartDataFromGeojson(sinistrosFeatures));
    } catch (error) {
        if (status) status.textContent = "Não foi possível carregar os sinistros reais agora.";
        window.RiscoIACharts?.updateReal(null);
    }
}

// ---------------------------------------------------------------------
// Gráficos Chart.js - "Sinistros por período" e "Vias com maior
// incidência" descrevem dados reais (GET /sinistros/geojson, ver
// carregarSinistrosReais acima), não previsões. Um conjunto demonstrativo
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

function computeChartDataFromGeojson(features) {
    if (!features || !features.length) return null;

    const periodCounts = {};
    const roadCounts = {};
    features.forEach((f) => {
        const p = f.properties;
        const turno = p.turno || "Não informado";
        periodCounts[turno] = (periodCounts[turno] || 0) + 1;
        if (p.logradouro) {
            roadCounts[p.logradouro] = (roadCounts[p.logradouro] || 0) + 1;
        }
    });

    const topRoads = Object.entries(roadCounts).sort((a, b) => b[1] - a[1]).slice(0, 8);
    return { periodData: periodCounts, roadsData: Object.fromEntries(topRoads) };
}

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
// Predição - heurística demonstrativa no frontend. O backend ainda não tem
// um modelo de IA nem endpoint de predição (o projeto, até aqui, só ingere
// e visualiza os dados oficiais - ver README); quando esse modelo existir,
// é só trocar o corpo desta função por uma chamada a ele.
// ---------------------------------------------------------------------
function updateResult(prob, factors, meta) {
    const card = document.getElementById("predictionResult");
    const tag = document.getElementById("riskTag");
    const title = document.getElementById("riskTitle");
    const percent = document.getElementById("riskPercent");
    const meter = document.getElementById("riskMeter");
    const why = document.getElementById("riskFactors");
    if (!card) return;

    const level = RiscoIA.levelFromProb(prob);
    tag.textContent = level === "alto" ? "RISCO ELEVADO" : level === "medio" ? "RISCO MÉDIO" : "RISCO BAIXO";
    card.className = `result-card ${level}`;
    percent.textContent = `${prob}% de probabilidade de sinistro`;
    title.textContent = level === "alto" ? "Atenção recomendada" : level === "medio" ? "Atenção moderada" : "Condição de menor risco";
    why.textContent = factors;
    meter.style.width = prob + "%";
    card.hidden = false;

    // Em vez de um MutationObserver "espionando" o DOM para descobrir que
    // uma previsão aconteceu, disparamos um evento explícito com os dados -
    // enhancements.js escuta esse evento para salvar o histórico.
    document.dispatchEvent(new CustomEvent("riscoia:prediction", {
        detail: { probabilidade: prob, risco: level, ...meta }
    }));
}

async function handlePrediction(e) {
    e.preventDefault();

    const via = document.getElementById("predVia").value;
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
        // Atraso artificial só para dar a sensação de "analisando" - o
        // cálculo em si (calculateFallback) é síncrono e local.
        await new Promise((resolve) => setTimeout(resolve, 400));

        const prob = RiscoIA.calculateFallback({ via, horario, clima, dia });
        const climaTexto = clima === "chuva" ? "Chuva intensa" : "Condição climática favorável";
        const horarioTexto = (horario === "pico-manha" || horario === "pico-noite") ? "horário de pico" : "horário fora do pico";
        updateResult(
            prob,
            `Fator principal: ${climaTexto} + ${horarioTexto}. Estimativa demonstrativa do frontend (o backend ainda não tem um modelo de IA de predição).`,
            { via, horario, clima, dia, origem: "Frontend demonstrativo" }
        );
    } finally {
        btn.disabled = false;
        txt.textContent = "Calcular Risco";
        spin?.classList.add("hidden");
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
// Widget "Risco agora" do dashboard: mesma ideia do botão acima, mas
// calculado para as 5 vias monitoradas de uma vez, com a heurística local
// (RiscoIA.calculateFallback) - sem chamar a API do modelo repetidamente
// só para popular um painel passivo do dashboard.
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

    const resultados = zoneData
        .map((z) => ({
            via: RiscoIA.LABELS.via[z.via] || z.via,
            prob: RiscoIA.calculateFallback({ via: z.via, horario, clima, dia })
        }))
        .sort((a, b) => b.prob - a.prob);

    title.textContent = `${dia}, ${RiscoIA.LABELS.horario[horario]} · ${RiscoIA.LABELS.clima[clima]} (${climaOrigem})`;
    const piorNivel = RiscoIA.levelFromProb(resultados[0].prob);
    badge.textContent = "RISCO " + piorNivel.toUpperCase();
    badge.className = "smart-badge " + piorNivel;

    grid.innerHTML = resultados.map((r) => {
        const nivel = RiscoIA.levelFromProb(r.prob);
        return `<div class="live-risk-item ${nivel}"><span class="live-risk-via">${r.via}</span><span class="live-risk-value">${r.prob}%</span></div>`;
    }).join("");
}

document.getElementById("refreshLiveRisk")?.addEventListener("click", renderLiveRisk);

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
});
