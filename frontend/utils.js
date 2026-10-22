/*
 * RiscoIA - utils.js
 * -------------------------------------------------------------------------
 * Camada compartilhada usada por script.js e enhancements.js (e testável
 * isoladamente via Node, sem precisar de navegador/DOM).
 *
 * Por que este arquivo existe:
 * - Autenticação real via backend (`POST /auth/login`, `POST /auth/register`,
 *   `GET /auth/me`): aqui ficam só os helpers de sessão (token JWT,
 *   expiração, usuário atual) usados por script.js/enhancements.js.
 * - Antes, o mapa (script.js) e o formulário de predição usavam dois
 *   vocabulários diferentes para "horário" e "via" (ex.: mapa usava "pico",
 *   predição usava "pico-manha"/"pico-noite"). Agora as duas telas usam as
 *   mesmas listas (VIA_OPTIONS, HORARIO_OPTIONS, CLIMA_OPTIONS) definidas
 *   aqui, então não têm mais como ficar dessincronizadas.
 */
(function (root, factory) {
    if (typeof module === "object" && module.exports) {
        module.exports = factory();
    } else {
        root.RiscoIA = factory();
    }
})(typeof window !== "undefined" ? window : globalThis, function () {
    "use strict";

    // ---------------------------------------------------------------------
    // Configuração
    // ---------------------------------------------------------------------
    // URL da API centralizada aqui: para apontar para outro backend (ou
    // ambiente de produção), troque só esta linha em vez de procurar por
    // "localhost" espalhado pelo código. Vazio = mesma origem (o frontend é
    // servido pela própria API FastAPI, ver `src/app/main.py`).
    const CONFIG = {
        API_BASE_URL: (typeof window !== "undefined" && window.RISCOIA_API_BASE_URL) || ""
    };

    function apiUrl(path) {
        return CONFIG.API_BASE_URL + path;
    }

    // ---------------------------------------------------------------------
    // Vocabulário único (via / horário / clima) usado pelo mapa,
    // pela predição e pelos relatórios.
    // ---------------------------------------------------------------------
    const VIA_OPTIONS = [
        { value: "francisco-junqueira", label: "Av. Francisco Junqueira" },
        { value: "dom-pedro", label: "Av. Dom Pedro I" },
        { value: "anhanguera", label: "Rod. Anhanguera" },
        { value: "centro", label: "Centro" },
        { value: "botanico", label: "Jardim Botânico" }
    ];

    const HORARIO_OPTIONS = [
        { value: "pico-manha", label: "07h-09h (pico manhã)", periodo: "Manhã" },
        { value: "fora-pico", label: "10h-16h (fora do pico)", periodo: "Tarde" },
        { value: "pico-noite", label: "17h-19h (pico noite)", periodo: "Noite" },
        { value: "madrugada", label: "00h-06h (madrugada)", periodo: "Madrugada" }
    ];

    const CLIMA_OPTIONS = [
        { value: "chuva", label: "Chuva" },
        { value: "sol", label: "Sol" },
        { value: "nublado", label: "Nublado" }
    ];

    // Mesmas categorias de `GET /risco/zonas?veiculo=` (ver src/ml/dados.py).
    const VEICULO_OPTIONS = [
        { value: "carro", label: "Carro" },
        { value: "moto", label: "Moto" },
        { value: "caminhao", label: "Caminhão" },
        { value: "onibus", label: "Ônibus" }
    ];

    // Nos <select> de dia da semana, o valor exibido já é o próprio rótulo
    // (não existe um slug separado como em via/horário/clima).
    const DIA_OPTIONS = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"];

    // Horas que cada faixa do formulário representa, para `GET /risco/simular`.
    // Seguem o rótulo exibido (ex.: "17h-19h"), não a extensão até 21h que
    // horarioAtualBucket() usa só para encaixar o relógio numa faixa.
    const HORARIO_HORAS = {
        "pico-manha": [7, 8, 9],
        "fora-pico": [10, 11, 12, 13, 14, 15, 16],
        "pico-noite": [17, 18, 19],
        "madrugada": [0, 1, 2, 3, 4, 5, 6]
    };

    function toLabelMap(options) {
        const map = {};
        options.forEach(function (opt) { map[opt.value] = opt.label; });
        return map;
    }

    const LABELS = {
        via: toLabelMap(VIA_OPTIONS),
        horario: toLabelMap(HORARIO_OPTIONS),
        clima: toLabelMap(CLIMA_OPTIONS),
        veiculo: toLabelMap(VEICULO_OPTIONS)
    };

    // "às segundas-feiras" ... "aos domingos", para frases como "esperados N
    // acidentes por ano às sextas-feiras".
    const DIA_NO_PLURAL = {
        "Segunda-feira": "às segundas-feiras", "Terça-feira": "às terças-feiras",
        "Quarta-feira": "às quartas-feiras", "Quinta-feira": "às quintas-feiras",
        "Sexta-feira": "às sextas-feiras", "Sábado": "aos sábados", "Domingo": "aos domingos"
    };
    function diaNoPlural(diaLabel) {
        return DIA_NO_PLURAL[diaLabel] || diaLabel;
    }

    // Índice usado pela API (`dia_semana`): 0 = segunda ... 6 = domingo,
    // mesma ordem de DIA_OPTIONS.
    function diaSemanaIndex(diaLabel) {
        return DIA_OPTIONS.indexOf(diaLabel);
    }

    // Nomes de via chegam da base oficial em maiúsculas e sem acento
    // ("AVENIDA DOUTOR FRANCISCO JUNQUEIRA"). Para exibir, capitaliza cada
    // palavra, mantém preposições em minúsculas e siglas de rodovia (SP, BR)
    // em maiúsculas.
    const PREPOSICOES = ["DE", "DA", "DO", "DAS", "DOS", "E"];
    function formatVia(nome) {
        return String(nome || "").trim().split(/\s+/).map(function (palavra, i) {
            const p = palavra.toUpperCase();
            if (/^(SP|BR|RP)$/.test(p) || /\d/.test(p)) return p;
            if (i > 0 && PREPOSICOES.includes(p)) return p.toLowerCase();
            return p.charAt(0) + p.slice(1).toLowerCase();
        }).join(" ");
    }

    // A API devolve "ALTO" | "MEDIO" | "BAIXO"; as classes de CSS do site
    // usam "alto" | "medio" | "baixo".
    function levelFromApi(nivel) {
        return String(nivel || "").toLowerCase() || "baixo";
    }

    function periodoFromHorario(horarioValue) {
        const found = HORARIO_OPTIONS.find(function (opt) { return opt.value === horarioValue; });
        return found ? found.periodo : null;
    }

    // ---------------------------------------------------------------------
    // Sessão: token JWT real emitido por `POST /auth/login` (ver
    // `src/app/core/security.py`). O backend já valida o token a cada
    // requisição; aqui só precisamos saber se ele expirou para decidir
    // quando mandar a pessoa de volta para o login.
    // ---------------------------------------------------------------------
    const SESSION_TOKEN = "token";
    const SESSION_EXPIRES = "riscoIA_session_expires";
    const SESSION_USER = "riscoIA_current_user";

    function normalize(value) {
        return String(value || "").trim().toLowerCase();
    }

    function isValidEmail(value) {
        // Checagem simples de formato (não substitui validação real por e-mail).
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value || "").trim());
    }

    function decodeJwtPayload(token) {
        try {
            const base64Url = token.split(".")[1];
            let base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
            while (base64.length % 4 !== 0) base64 += "=";
            const json = typeof atob !== "undefined"
                ? decodeURIComponent(atob(base64).split("").map(function (c) {
                    return "%" + c.charCodeAt(0).toString(16).padStart(2, "0");
                }).join(""))
                : Buffer.from(base64, "base64").toString("utf-8");
            return JSON.parse(json);
        } catch (e) {
            return null;
        }
    }

    // `user` é o corpo de `GET /auth/me` (username, role, name, email).
    function startSession(token, user) {
        const payload = decodeJwtPayload(token);
        // `exp` do JWT vem em segundos; se por algum motivo não der para
        // decodificar, expira em 1h (mesmo padrão do backend).
        const expiresAt = payload && payload.exp ? payload.exp * 1000 : Date.now() + 60 * 60 * 1000;
        sessionStorage.setItem(SESSION_TOKEN, token);
        sessionStorage.setItem(SESSION_EXPIRES, String(expiresAt));
        sessionStorage.setItem(SESSION_USER, JSON.stringify(user));
    }

    function getToken() {
        return sessionStorage.getItem(SESSION_TOKEN);
    }

    function authHeader() {
        const token = getToken();
        return token ? { Authorization: "Bearer " + token } : {};
    }

    function isSessionValid() {
        const token = sessionStorage.getItem(SESSION_TOKEN);
        const expiresAt = Number(sessionStorage.getItem(SESSION_EXPIRES) || 0);
        return Boolean(token) && Date.now() < expiresAt;
    }

    function getSessionUser() {
        try {
            return JSON.parse(sessionStorage.getItem(SESSION_USER));
        } catch (e) {
            return null;
        }
    }

    function clearSession() {
        sessionStorage.removeItem(SESSION_TOKEN);
        sessionStorage.removeItem(SESSION_EXPIRES);
        sessionStorage.removeItem(SESSION_USER);
    }

    // ---------------------------------------------------------------------
    // UI helpers
    // ---------------------------------------------------------------------
    function showMessage(el, text, type) {
        if (!el) return;
        el.textContent = text;
        el.className = "message " + type;
    }

    // Texto vindo da base (nomes de via etc.) antes de entrar em innerHTML /
    // popups do Leaflet.
    function escapeHtml(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    function clearMessage(el) {
        if (!el) return;
        el.textContent = "";
        el.className = "message hidden";
    }

    // ---------------------------------------------------------------------
    // Lógica de predição (pura, sem DOM - por isso é testável direto)
    // ---------------------------------------------------------------------
    function calculateFallback(data) {
        let score = 30;
        if (data.horario === "pico-manha" || data.horario === "pico-noite") score += 25;
        if (data.clima === "chuva") score += 20;
        if (data.via === "francisco-junqueira") score += 10;
        if (data.via === "anhanguera") score += 8;

        // Dia da semana: sexta tende a ter mais tráfego/saídas noturnas;
        // fins de semana tendem a ter menos tráfego de deslocamento (embora
        // possam ter mais risco noturno em outros contextos). É uma
        // heurística demonstrativa, não um resultado de modelo estatístico.
        if (data.dia === "Sexta-feira") score += 5;
        if (data.dia === "Sábado" || data.dia === "Domingo") score -= 5;

        return Math.max(5, Math.min(97, score));
    }

    function levelFromProb(prob) {
        return prob >= 70 ? "alto" : prob >= 40 ? "medio" : "baixo";
    }

    // Filtro das zonas de risco do mapa (`GET /risco/zonas`): `nivel` é
    // "todos", "alto" ou "alto-medio"; `soEmAlta` mostra só as zonas cuja
    // ocorrência recente está acima do próprio histórico.
    function zonaVisivel(props, filtros) {
        const nivel = (filtros && filtros.nivel) || "todos";
        const n = levelFromApi(props.nivel_risco);
        if (nivel === "alto" && n !== "alto") return false;
        if (nivel === "alto-medio" && n === "baixo") return false;
        return !(filtros && filtros.soEmAlta) || Boolean(props.em_alta);
    }

    // ---------------------------------------------------------------------
    // "Tempo real" honesto: não existe fluxo contínuo de sinistros ao vivo
    // (o InfoSiga só publica um arquivo novo por mês), então o que dá para
    // ter em tempo real é a CONDIÇÃO atual (hora + clima reais) alimentando
    // o modelo/heurística de risco - não a ocorrência de sinistros em si.
    // ---------------------------------------------------------------------

    // Coordenadas aproximadas do centro de Ribeirão Preto/SP, usadas para
    // consultar o clima atual na Open-Meteo (API pública, sem chave, com
    // CORS liberado para uso direto do navegador).
    const RIBEIRAO_PRETO_COORDS = { latitude: -21.1775, longitude: -47.8103 };

    function diaAtualPtBR(date) {
        const d = date || new Date();
        // getDay(): 0 = domingo ... 6 = sábado
        const index = [6, 0, 1, 2, 3, 4, 5][d.getDay()]; // reordena para bater com DIA_OPTIONS (segunda primeiro)
        return DIA_OPTIONS[index];
    }

    function horarioAtualBucket(date) {
        const hour = (date || new Date()).getHours();
        if (hour >= 7 && hour <= 9) return "pico-manha";
        if (hour >= 10 && hour <= 16) return "fora-pico";
        // As faixas de horário do formulário cobrem só 07h-19h + madrugada;
        // as horas entre 20h e 23h ficam fora dos rótulos originais, então
        // são tratadas aqui como extensão do horário de pico noturno.
        if (hour >= 17 && hour <= 21) return "pico-noite";
        return "madrugada"; // 22h-06h
    }

    function climaFromWeatherCode(code) {
        // Códigos meteorológicos WMO usados pela Open-Meteo.
        if (code === 0) return "sol";
        if ([1, 2, 3, 45, 48].includes(code)) return "nublado";
        return "chuva"; // 51+ cobre garoa, chuva, pancadas e tempestade
    }

    async function fetchLiveWeatherClima() {
        const { latitude, longitude } = RIBEIRAO_PRETO_COORDS;
        const url = `https://api.open-meteo.com/v1/forecast?latitude=${latitude}&longitude=${longitude}&current=weather_code&timezone=America%2FSao_Paulo`;
        const response = await fetch(url);
        if (!response.ok) throw new Error("Falha ao consultar o clima atual");
        const data = await response.json();
        return climaFromWeatherCode(data.current.weather_code);
    }

    return {
        CONFIG: CONFIG,
        VIA_OPTIONS: VIA_OPTIONS,
        HORARIO_OPTIONS: HORARIO_OPTIONS,
        CLIMA_OPTIONS: CLIMA_OPTIONS,
        VEICULO_OPTIONS: VEICULO_OPTIONS,
        DIA_OPTIONS: DIA_OPTIONS,
        HORARIO_HORAS: HORARIO_HORAS,
        LABELS: LABELS,
        diaSemanaIndex: diaSemanaIndex,
        diaNoPlural: diaNoPlural,
        formatVia: formatVia,
        levelFromApi: levelFromApi,
        periodoFromHorario: periodoFromHorario,
        apiUrl: apiUrl,
        normalize: normalize,
        isValidEmail: isValidEmail,
        decodeJwtPayload: decodeJwtPayload,
        startSession: startSession,
        getToken: getToken,
        authHeader: authHeader,
        isSessionValid: isSessionValid,
        getSessionUser: getSessionUser,
        clearSession: clearSession,
        showMessage: showMessage,
        clearMessage: clearMessage,
        escapeHtml: escapeHtml,
        calculateFallback: calculateFallback,
        levelFromProb: levelFromProb,
        zonaVisivel: zonaVisivel,
        diaAtualPtBR: diaAtualPtBR,
        horarioAtualBucket: horarioAtualBucket,
        climaFromWeatherCode: climaFromWeatherCode,
        fetchLiveWeatherClima: fetchLiveWeatherClima
    };
});
