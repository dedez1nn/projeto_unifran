
"use strict";

/*
 * RiscoIA - camada adicional
 * Não substitui o JavaScript original. Acrescenta:
 * - recuperação de senha para demonstração frontend
 * - estados de erro/offline e estado vazio
 * - melhorias de acessibilidade e teclado
 */

(function () {
    // normalize/showMessage agora vêm de utils.js (objeto global RiscoIA),
    // para não ter duas cópias divergentes da mesma lógica.
    const { showMessage } = RiscoIA;

    // Botões Mostrar/Ocultar também funcionam na tela de recuperação.
    document.querySelectorAll(".password-toggle").forEach(button => {
        button.addEventListener("click", () => {
            const input = document.getElementById(button.dataset.target);
            if (!input) return;

            const showing = input.type === "password";
            input.type = showing ? "text" : "password";
            button.textContent = showing ? "Ocultar" : "Mostrar";
            button.setAttribute("aria-label", showing ? "Ocultar senha" : "Mostrar senha");
        });
    });

    // Recuperação de senha: o backend real (`src/app/api/routes/auth.py`) não
    // tem endpoint de redefinição de senha (isso exigiria um serviço de
    // e-mail, que está fora do escopo atual do projeto - ver README/docs).
    // A versão anterior deste formulário simulava a troca alterando um
    // "banco" de usuários guardado no localStorage, mas isso não tinha mais
    // nenhum efeito real depois que login/cadastro passaram a falar com a
    // API de verdade - manter aquele fluxo seria enganoso (a pessoa acharia
    // que trocou a senha, mas a senha de fato, no backend, continuaria a
    // mesma). Por isso a tela agora só orienta a pessoa a procurar o
    // administrador do sistema, deixando claro que o recurso ainda não está
    // disponível de ponta a ponta.
    const recoveryForm = document.getElementById("recoveryForm");
    if (recoveryForm) {
        const message = document.getElementById("recoveryMessage");

        recoveryForm.addEventListener("submit", function (event) {
            event.preventDefault();
            showMessage(
                message,
                "A recuperação de senha por e-mail ainda não está disponível nesta versão. " +
                "Entre em contato com o administrador do sistema para redefinir sua senha.",
                "error"
            );
        });
    }

    // Estados de conexão e dados.
    const status = document.getElementById("systemStatus");
    const statusTitle = document.getElementById("systemStatusTitle");
    const statusText = document.getElementById("systemStatusText");
    const retryButton = document.getElementById("retryStatus");
    const emptyState = document.getElementById("dataEmptyState");
    const emptyAction = document.getElementById("emptyStateAction");

    // navigator.onLine reflete apenas o estado da interface de rede do
    // sistema operacional (Wi-Fi/cabo ligado ou não) - ele pode informar
    // "offline" mesmo quando o site está funcionando normalmente (por isso
    // o aviso aparecia mesmo com o RiscoIA rodando sem problemas). Para
    // evitar esse falso positivo, além do navigator.onLine confirmamos a
    // conexão de verdade com uma requisição real antes de exibir o aviso.
    let connectivityCheckToken = 0;

    function reallyOffline() {
        const requestId = ++connectivityCheckToken;
        return fetch(location.href, { method: "HEAD", cache: "no-store" })
            .then(() => requestId !== connectivityCheckToken ? null : false)
            .catch(() => requestId !== connectivityCheckToken ? null : true);
    }

    function updateConnectionState() {
        if (!status) return;

        if (navigator.onLine) {
            status.hidden = true;
            return;
        }

        // O navegador acha que caiu a conexão: confirma antes de alarmar o usuário.
        reallyOffline().then(offline => {
            if (offline === null) return; // uma checagem mais nova já respondeu por nós
            if (offline) {
                status.hidden = false;
                statusTitle.textContent = "Sem conexão com a internet";
                statusText.textContent = "Alguns dados externos podem não estar disponíveis enquanto estiver offline.";
            } else {
                status.hidden = true;
            }
        });
    }

    function showTemporaryEmptyState() {
        if (!emptyState) return;
        emptyState.hidden = false;
        setTimeout(function () {
            if (navigator.onLine) {
                emptyState.hidden = true;
            }
        }, 2500);
    }

    if (status) {
        window.addEventListener("online", updateConnectionState);
        window.addEventListener("offline", updateConnectionState);
        updateConnectionState();
    }

    if (retryButton) {
        retryButton.addEventListener("click", function () {
            if (navigator.onLine) {
                status.hidden = true;
                showTemporaryEmptyState();
            } else {
                updateConnectionState();
            }
        });
    }

    if (emptyAction) {
        emptyAction.addEventListener("click", function () {
            emptyState.hidden = true;
        });
    }

    // Menu mobile: estado aria-expanded e suporte ao teclado.
    const mobileMenu = document.getElementById("mobileMenu");
    const navMenu = document.getElementById("mainNavigation");

    if (mobileMenu && navMenu) {
        mobileMenu.addEventListener("click", function () {
            const expanded = mobileMenu.getAttribute("aria-expanded") === "true";
            mobileMenu.setAttribute("aria-expanded", String(!expanded));
            mobileMenu.setAttribute("aria-label", expanded ? "Abrir menu" : "Fechar menu");
        });
    }

    // Scrollspy: destaca no menu (sublinhado azul) a seção que está sendo
    // vista no momento, do mesmo jeito que "Início" já vinha fixo antes -
    // agora isso acontece para qualquer seção (Mapa de Risco, Sinistros,
    // Análises, Sobre o Projeto, Metodologia) conforme a rolagem da página.
    const scrollSpyLinks = Array.from(document.querySelectorAll('.nav-menu .nav-link[href^="#"]'));

    if (scrollSpyLinks.length) {
        const scrollSpyTargets = scrollSpyLinks
            .map(function (link) {
                return { link: link, el: document.getElementById(link.getAttribute("href").slice(1)) };
            })
            .filter(function (t) { return t.el; });

        function setActiveNavLink(activeLink) {
            scrollSpyLinks.forEach(function (link) {
                link.classList.toggle("active", link === activeLink);
            });
        }

        function updateActiveNavLink() {
            const headerOffset = 130; // altura aproximada do cabeçalho fixo
            let current = scrollSpyTargets[0] ? scrollSpyTargets[0].link : null;

            scrollSpyTargets.forEach(function (target) {
                const top = target.el.getBoundingClientRect().top;
                if (top - headerOffset <= 0) {
                    current = target.link;
                }
            });

            // Perto do fim da página, garante que a última seção fique ativa
            // mesmo que sobre um espaço em branco depois dela (ex.: rodapé curto).
            const scrolledToBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4;
            if (scrolledToBottom) {
                current = scrollSpyTargets[scrollSpyTargets.length - 1].link;
            }

            if (current) setActiveNavLink(current);
        }

        scrollSpyLinks.forEach(function (link) {
            link.addEventListener("click", function () {
                setActiveNavLink(link);
            });
        });

        window.addEventListener("scroll", updateActiveNavLink, { passive: true });
        window.addEventListener("resize", updateActiveNavLink);
        updateActiveNavLink();
    }

    // Acesso rápido à recuperação de senha.
    const forgotLink = document.getElementById("forgotPasswordLink");
    if (forgotLink) {
        forgotLink.addEventListener("click", function () {
            window.location.href = "forgot-password.html";
        });
    }

    // Respeita preferência de redução de movimento sem apagar as animações existentes.
    const prefersReducedMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReducedMotion) {
        document.documentElement.classList.add("reduce-motion");
    }

    // Brilho que acompanha o cursor pela tela (efeito visual, sem interferir em cliques).
    // Só ativa em dispositivos com mouse de verdade ("pointer: fine") e quando o usuário
    // não pediu para reduzir animações.
    const hasFinePointer = window.matchMedia && window.matchMedia("(pointer: fine)").matches;
    if (hasFinePointer && !prefersReducedMotion) {
        const cursorGlow = document.createElement("div");
        cursorGlow.className = "cursor-glow";
        cursorGlow.setAttribute("aria-hidden", "true");
        document.body.appendChild(cursorGlow);

        let targetX = window.innerWidth / 2;
        let targetY = window.innerHeight / 2;
        let currentX = targetX;
        let currentY = targetY;
        let isVisible = false;

        function showGlow() {
            if (isVisible) return;
            isVisible = true;
            cursorGlow.style.opacity = "1";
        }

        function hideGlow() {
            isVisible = false;
            cursorGlow.style.opacity = "0";
        }

        window.addEventListener("pointermove", function (event) {
            targetX = event.clientX;
            targetY = event.clientY;
            showGlow();
        });

        document.addEventListener("mouseleave", hideGlow);
        window.addEventListener("blur", hideGlow);

        (function followCursor() {
            // Suaviza o movimento (efeito de "arraste") em vez de saltar direto para o cursor.
            currentX += (targetX - currentX) * 0.16;
            currentY += (targetY - currentY) * 0.16;
            cursorGlow.style.transform = "translate3d(" + currentX + "px, " + currentY + "px, 0)";
            requestAnimationFrame(followCursor);
        })();
    }
})();

/* =====================================================
   RiscoIA - histórico, indicadores e relatórios
===================================================== */
(function () {
    const HISTORY_KEY = "riscoIA_prediction_history";
    // Rótulos vêm de RiscoIA.LABELS (utils.js) - a mesma fonte usada pelo
    // mapa e pela predição, então não tem mais como o relatório mostrar um
    // nome de via/horário diferente do que aparece nas outras telas.
    const labels = RiscoIA.LABELS;
    const riskNames = { alto: "ALTO", medio: "MÉDIO", baixo: "BAIXO" };

    function getHistory() {
        try {
            return JSON.parse(localStorage.getItem(HISTORY_KEY)) || [];
        } catch (e) {
            return [];
        }
    }

    function saveHistory(items) {
        localStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(-100)));
    }

    function formatDate(iso) {
        try {
            return new Date(iso).toLocaleString("pt-BR");
        } catch (e) {
            return iso;
        }
    }

    // Antes, este módulo descobria que uma previsão tinha acontecido
    // observando (via MutationObserver) o card de resultado mudar de classe/
    // atributo "hidden" - um jeito indireto e frágil de reagir a um evento.
    // Agora script.js dispara um evento "riscoia:prediction" assim que a
    // predição é calculada, com os dados já prontos, e só escutamos ele.
    function savePredictionFromDetail(detail) {
        const item = {
            id: Date.now() + Math.random(),
            createdAt: new Date().toISOString(),
            via: detail.via || "",
            horario: detail.horario || "",
            clima: detail.clima || "",
            dia: detail.dia || "",
            probabilidade: Math.max(0, Math.min(100, Number(detail.probabilidade) || 0)),
            risco: detail.risco || RiscoIA.levelFromProb(Number(detail.probabilidade) || 0),
            origem: detail.origem || "Frontend demonstrativo"
        };
        const history = getHistory();
        history.push(item);
        saveHistory(history);
        updateAll();
    }

    function updateDashboard() {
        const total = document.getElementById("smartTotal");
        if (!total) return;

        const h = getHistory();
        const counts = { alto: 0, medio: 0, baixo: 0 };
        h.forEach((x) => { if (counts[x.risco] !== undefined) counts[x.risco]++; });

        document.getElementById("smartTotal").textContent = h.length;
        document.getElementById("smartHigh").textContent = counts.alto;
        document.getElementById("smartMedium").textContent = counts.medio;
        document.getElementById("smartLow").textContent = counts.baixo;

        // "Sinistros por período"/"Vias com maior incidência" (script.js:
        // window.RiscoIACharts) mostram dados reais de GET /sinistros/geojson,
        // não o histórico de simulações - por isso não são atualizados aqui.

        const last = h[h.length - 1];
        if (!last) return;

        const title = document.getElementById("latestRiskTitle");
        const text = document.getElementById("latestRiskText");
        const badge = document.getElementById("latestRiskBadge");
        const meter = document.getElementById("latestRiskMeter");
        const alertTitle = document.getElementById("smartAlertTitle");
        const alertText = document.getElementById("smartAlertText");
        const name = riskNames[last.risco] || last.risco.toUpperCase();

        title.textContent = (labels.via[last.via] || last.via) + " • RISCO " + name;
        badge.textContent = "RISCO " + name;
        badge.className = "smart-badge " + last.risco;
        meter.style.width = last.probabilidade + "%";
        text.textContent = `Probabilidade estimada de ${last.probabilidade}%, registrada em ${formatDate(last.createdAt)}. Origem: ${last.origem}.`;

        if (last.risco === "alto") {
            alertTitle.textContent = "Atenção recomendada";
            alertText.textContent = "A última previsão atingiu nível elevado. Consulte a simulação e o histórico para analisar os fatores envolvidos.";
        } else if (last.risco === "medio") {
            alertTitle.textContent = "Atenção moderada";
            alertText.textContent = "A última previsão ficou em nível médio. Compare a região com outras previsões para identificar padrões.";
        } else {
            alertTitle.textContent = "Condição de menor risco";
            alertText.textContent = "A última previsão ficou em nível baixo no conjunto demonstrativo.";
        }
    }

    function reportRender() {
        const body = document.getElementById("historyTableBody");
        if (!body) return;

        const riskFilter = document.getElementById("reportRiskFilter")?.value || "todos";
        const dateFilter = document.getElementById("reportDateFilter")?.value || "";
        const viaFilter = document.getElementById("reportViaFilter")?.value || "todos";

        const all = getHistory();
        const filtered = all.filter((x) =>
            (riskFilter === "todos" || x.risco === riskFilter) &&
            (!dateFilter || x.createdAt.slice(0, 10) === dateFilter) &&
            (viaFilter === "todos" || x.via === viaFilter)
        );

        const counts = { alto: 0, medio: 0, baixo: 0 };
        all.forEach((x) => { if (counts[x.risco] !== undefined) counts[x.risco]++; });
        const statIds = ["reportTotal", "reportHigh", "reportMedium", "reportLow"];
        const statVals = [all.length, counts.alto, counts.medio, counts.baixo];
        statIds.forEach((id, i) => {
            const el = document.getElementById(id);
            if (el) el.textContent = statVals[i];
        });

        body.innerHTML = "";
        filtered.slice().reverse().forEach((x) => {
            const tr = document.createElement("tr");
            tr.innerHTML = `<td>${formatDate(x.createdAt)}</td><td>${labels.via[x.via] || x.via}</td><td>${labels.horario[x.horario] || x.horario}</td><td>${labels.clima[x.clima] || x.clima}</td><td>${x.dia || "-"}</td><td><span class="risk-pill ${x.risco}">${riskNames[x.risco] || x.risco}</span></td><td>${x.probabilidade}%</td><td>${x.origem}</td>`;
            body.appendChild(tr);
        });

        const empty = document.getElementById("historyEmpty");
        if (empty) empty.hidden = filtered.length > 0;

        const comp = document.getElementById("roadComparison");
        if (comp) {
            const groups = {};
            filtered.forEach((x) => {
                const name = labels.via[x.via] || x.via;
                if (!groups[name]) groups[name] = { n: 0, sum: 0 };
                groups[name].n++;
                groups[name].sum += x.probabilidade;
            });
            const rows = Object.entries(groups)
                .map(([name, v]) => ({ name, n: v.n, avg: Math.round(v.sum / v.n) }))
                .sort((a, b) => b.avg - a.avg);
            comp.innerHTML = rows.length
                ? rows.map((r) => `<article class="comparison-card"><h3>${r.name}</h3><p>${r.n} previsão(ões) • média de ${r.avg}%</p><div class="comparison-bar"><span style="width:${r.avg}%"></span></div></article>`).join("")
                : '<div class="history-empty">Ainda não há dados suficientes para comparar regiões.</div>';
        }
    }

    function exportCSV() {
        const h = getHistory();
        if (!h.length) {
            alert("Não há previsões para exportar.");
            return;
        }
        const header = ["Data", "Via", "Horario", "Clima", "Dia", "Risco", "Probabilidade", "Origem"];
        const rows = h.map((x) => [
            formatDate(x.createdAt), labels.via[x.via] || x.via, labels.horario[x.horario] || x.horario,
            labels.clima[x.clima] || x.clima, x.dia, riskNames[x.risco] || x.risco, x.probabilidade + "%", x.origem
        ]);
        const csv = [header, ...rows].map((r) => r.map((v) => `"${String(v).replaceAll('"', '""')}"`).join(",")).join("\n");
        const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8;" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "riscoIA-historico.csv";
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    }

    function populateViaFilter() {
        const select = document.getElementById("reportViaFilter");
        if (!select || select.dataset.populated === "true") return;
        RiscoIA.VIA_OPTIONS.forEach((opt) => {
            const option = document.createElement("option");
            option.value = opt.value;
            option.textContent = opt.label;
            select.appendChild(option);
        });
        select.dataset.populated = "true";
    }

    function updateAll() {
        updateDashboard();
        reportRender();
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.addEventListener("riscoia:prediction", (e) => savePredictionFromDetail(e.detail));

        populateViaFilter();
        document.getElementById("reportRiskFilter")?.addEventListener("change", reportRender);
        document.getElementById("reportDateFilter")?.addEventListener("change", reportRender);
        document.getElementById("reportViaFilter")?.addEventListener("change", reportRender);
        document.getElementById("exportCsv")?.addEventListener("click", exportCSV);
        document.getElementById("printReport")?.addEventListener("click", () => window.print());
        document.getElementById("clearHistory")?.addEventListener("click", () => {
            if (confirm("Deseja apagar todo o histórico local de previsões?")) {
                localStorage.removeItem(HISTORY_KEY);
                updateAll();
            }
        });
        updateAll();
    });

    window.RiscoIAHistory = { getHistory, updateAll };
})();
